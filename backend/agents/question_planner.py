"""Question Planner — decides the single next intake question.

Uses the LLM, but the *stopping condition* is computed in code: the required
field list comes from hospital.yaml and is checked against facts already in the
database. The model chooses phrasing; it does not get to decide that intake is
finished.
"""
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from models import AllergyMedication, IntakeMessage, PatientFact
from schemas.agent_outputs import NextQuestion
from services import hospital_config
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

# Hard ceiling on follow-ups. A model that keeps failing to extract a field
# would otherwise ask about it forever with no way for the patient to finish.
# Stopping and routing the gap to a clinician is the documented behaviour:
# missing information belongs in human review, not in an unescapable loop.
#
# With `_settle_last_question` doing its job each field is asked once, so this
# is a backstop rather than the thing that ends a conversation.
MAX_ASSISTANT_QUESTIONS = 12

# How a field gets closed when the patient answered but no fact came out of it.
# Three different things, deliberately not collapsed into one: a denial is
# clinical information ("no known drug allergies" belongs in the chart), a
# decline is not, and a reply the extractor could not use is neither — writing
# "none reported" for that would put a denial in the record the patient never
# made.
NONE_REPORTED = "None reported by patient"
DECLINED = "Declined to answer"
NOT_CAPTURED = "Answered — see the intake transcript"

# A plain no. Matched in code because the consequence is a line in a clinical
# record, and that must not depend on a model being up or in a good mood.
DENIAL_OPENERS = ("no", "nope", "nah", "none", "nothing", "negative", "n/a", "nil")
DENIAL_PHRASES = (
    "don't have any",
    "do not have any",
    "dont have any",
    "no known",
    "none at all",
    "not that i know",
    "nothing like that",
    "never had",
    "no history",
)

# The patient asking us to stop. Matched in code, not by the model: it has to
# work when the LLM is degraded, which is exactly when the repetition it guards
# against is most likely.
MOVE_ON_SIGNALS = (
    "repeating",
    "repeat",
    "already asked",
    "already told",
    "already answered",
    "asked me that",
    "same question",
    "move on",
    "move to the next",
    "next step",
    "go ahead",
    "stop asking",
    "skip this",
)

# Always sent when intake ends, so a finished conversation never looks frozen.
# Returning an empty question used to store no message at all, which the
# patient sees as the assistant simply not replying.
CLOSING = (
    "Thank you — that is everything I need. I am sending your answers to the "
    "care team now, and a clinician will review them before anything else "
    "happens."
)
CLOSING_WITH_GAPS = (
    "Thank you — I will pass on what you have told me. Anything still missing "
    "will be picked up by the clinician who reviews your case."
)

SYSTEM = """You are the intake assistant for a medical clinic, talking to a patient.

Ask exactly ONE short, plain-language question at a time to collect the missing \
information listed by the caller. Be warm and brief.

Hard rules:
- Never diagnose, never suggest treatment, never interpret test results.
- Never tell the patient how urgent their case is.
- If the patient describes a life-threatening emergency, your question must be to \
tell them to contact emergency services immediately.
- Ask only about the missing fields you are given.
- Reply with the question itself and nothing else: no preamble, no quotes, no \
list, no explanation. It is read aloud verbatim."""

# Which fact kinds satisfy which required field.
FIELD_SATISFIED_BY = {
    "reason_for_visit": {"reason_for_visit"},
    "symptom": {"symptom"},
    "duration": {"duration"},
    "history": {"history", "condition"},
    "contact_preference": {"contact_preference"},
}

FIELD_PROMPTS = {
    "reason_for_visit": "why they are seeking care today",
    "symptom": "what symptoms they are experiencing",
    "duration": "how long the symptoms have lasted",
    "name": "their full name, so the clinic can identify their record",
    "age": "their age",
    "gender": "their gender",
    "history": "relevant past medical conditions",
    "medication": "any medications they currently take",
    "allergy": "any allergies they have",
    "contact_preference": "how they prefer to be contacted",
}


def missing_fields(db: Session, case_id) -> list[str]:
    """Required fields with nothing recorded against them yet. Pure DB check."""
    facts = db.query(PatientFact).filter(PatientFact.case_id == case_id).all()
    entries = db.query(AllergyMedication).filter(
        AllergyMedication.case_id == case_id
    ).all()

    present_kinds = {f.kind for f in facts}
    has_allergy = any(e.kind == "allergy" for e in entries)
    has_medication = any(e.kind == "medication" for e in entries)

    missing = []
    for field in hospital_config.required_intake_fields():
        if field == "allergy":
            satisfied = has_allergy
        elif field == "medication":
            satisfied = has_medication
        else:
            satisfied = bool(FIELD_SATISFIED_BY.get(field, {field}) & present_kinds)
        if not satisfied:
            missing.append(field)
    return missing


def _record_answer(db: Session, case_id, field: str, value: str, turn_index: int) -> None:
    """Store a denial or a decline as the answer to `field`.

    Written as a normal row so it satisfies `missing_fields` by the same rule
    everything else does — no second notion of "answered" to keep in step, and
    the clinician sees "None reported by patient" rather than a silent gap.
    """
    if field in {"allergy", "medication"}:
        db.add(
            AllergyMedication(
                case_id=case_id,
                kind=field,
                name=value,
                reaction_or_dose=None,
                source_turn=turn_index,
            )
        )
    else:
        # `field` is always one of the kinds that satisfies it (see
        # FIELD_SATISFIED_BY), so no lookup is needed and none is guessed at.
        db.add(
            PatientFact(
                case_id=case_id,
                kind=field,
                value=value,
                source_turn=turn_index,
                confidence=1.0,
            )
        )
    db.commit()


def wants_to_move_on(message: str) -> bool:
    """Is the patient telling us to stop asking?"""
    lowered = message.lower()
    return any(signal in lowered for signal in MOVE_ON_SIGNALS)


def is_denial(message: str) -> bool:
    """Did the patient say they have none of this?

    Only a leading "no" or an explicit phrase counts. Anything else is treated
    as a reply we failed to understand rather than as a denial — recording
    "none reported" for a patient who actually described something would put a
    statement in their record that they never made.
    """
    lowered = message.strip().lower()
    first = lowered.replace(",", " ").replace(".", " ").split()
    if first and first[0] in DENIAL_OPENERS:
        return True
    return any(phrase in lowered for phrase in DENIAL_PHRASES)


def _settle_last_question(db: Session, case_id, session_id) -> None:
    """Close off the question the patient has just answered.

    **This is the fix for the repeat loop.** The extractor records only what a
    patient stated, so "no, I don't have any of those" produces no row at all —
    and a field with no row reads as never asked. The planner would then ask it
    again, reworded by the model each time, until the question ceiling stopped
    the conversation dead.

    Every assistant question records the field it was for, so here we can tell
    the two apart: if the field it asked about is still empty after the patient
    replied, the reply was a denial, and it is recorded as one.
    """
    asked = (
        db.query(IntakeMessage)
        .filter(
            IntakeMessage.session_id == session_id,
            IntakeMessage.role == "assistant",
            IntakeMessage.asks_field.isnot(None),
        )
        .order_by(IntakeMessage.turn_index.desc())
        .first()
    )
    if asked is None:
        return

    reply = (
        db.query(IntakeMessage)
        .filter(
            IntakeMessage.session_id == session_id,
            IntakeMessage.role == "patient",
            IntakeMessage.turn_index > asked.turn_index,
        )
        .order_by(IntakeMessage.turn_index)
        .first()
    )
    if reply is None:  # still waiting on them
        return
    if asked.asks_field not in missing_fields(db, case_id):
        return  # they answered with something the extractor understood

    if wants_to_move_on(reply.content):
        value = DECLINED
    elif is_denial(reply.content):
        value = NONE_REPORTED
    else:
        # They answered something, and the extractor made nothing of it. The
        # field still has to close or the question repeats forever, but the
        # record must not claim they denied it — point the clinician at what
        # was actually said instead.
        value = NOT_CAPTURED
    _record_answer(db, case_id, asked.asks_field, value, reply.turn_index)
    logger.info(
        "Intake field %r settled as %r from turn %s",
        asked.asks_field,
        value,
        reply.turn_index,
    )


def _on_file(db: Session, case_id) -> list[str]:
    """Everything already collected, for the prompt.

    The planner is told what is known as well as what is missing: the model
    choosing the wording is the same model that will happily re-ask something
    it can see three lines up unless the answer is put in front of it.
    """
    facts = (
        db.query(PatientFact)
        .filter(PatientFact.case_id == case_id)
        .order_by(PatientFact.source_turn)
        .all()
    )
    entries = (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case_id)
        .order_by(AllergyMedication.source_turn)
        .all()
    )
    return [f"{f.kind}: {f.value}" for f in facts] + [
        f"{e.kind}: {e.name}" for e in entries
    ]


async def plan_next_question(
    db: Session,
    case_id,
    session_id,
    transcript: list[dict],
    on_token: Callable[[str], None] | None = None,
) -> NextQuestion:
    """Return the next question, or `complete=True` when nothing is outstanding.

    This is the one agent whose output the patient reads, so it is the one
    agent that streams. `on_token` receives each chunk as the model produces
    it; the return value is still the whole question, and it is still the
    return value that gets persisted. Passing nothing simply generates the
    same reply without anybody watching.

    Free text rather than constrained JSON: `complete` and `missing_fields`
    are overwritten below because code owns the stopping condition, and
    `reason` is written here — which left the question as the only field the
    model actually decided. A schema bought nothing and cannot be streamed.
    """
    # Before deciding what is missing, close off what was just answered — a
    # denial is an answer, and treating it as a gap is what made the planner
    # loop. Everything below then works off an accurate field list.
    _settle_last_question(db, case_id, session_id)

    outstanding = missing_fields(db, case_id)

    if not outstanding:
        return NextQuestion(
            complete=True,
            question=CLOSING,
            missing_fields=[],
            reason="All required intake fields have been collected.",
        )

    asked = sum(1 for turn in transcript if turn.get("role") == "assistant")
    if asked >= MAX_ASSISTANT_QUESTIONS:
        return NextQuestion(
            complete=True,
            question=CLOSING_WITH_GAPS,
            missing_fields=outstanding,
            reason=(
                f"Stopped after {asked} questions with "
                f"{len(outstanding)} field(s) still outstanding. The gaps are "
                f"recorded as missing information for the clinician."
            ),
        )

    field = outstanding[0]
    described = [FIELD_PROMPTS.get(f, f) for f in outstanding]
    history = "\n".join(f"{m['role']}: {m['content']}" for m in transcript[-8:])

    # Everything the model needs in order not to repeat itself: what is on
    # file, and what it has already asked. Prompt tokens are cheap — they are
    # processed hundreds of times faster than they are generated — so this is
    # a much better trade than another wasted question.
    on_file = _on_file(db, case_id)
    already_asked = [
        turn["content"] for turn in transcript if turn.get("role") == "assistant"
    ]

    user = (
        f"Conversation so far:\n{history or '(nothing yet)'}\n\n"
        f"Already on file — do NOT ask about any of this again:\n"
        f"{chr(10).join('- ' + item for item in on_file) or '- (nothing yet)'}\n\n"
        f"Questions you have already asked — do not repeat any of them, and do "
        f"not ask a reworded version that means the same thing:\n"
        f"{chr(10).join('- ' + q for q in already_asked) or '- (none yet)'}\n\n"
        f"Still missing: {', '.join(described)}.\n\n"
        f"Ask one question about: {described[0]}."
    )

    question = ""
    try:
        async for chunk in llm.stream_text(SYSTEM, user):
            question += chunk
            if on_token:
                on_token(chunk)
        question = question.strip().strip('"')
        if not question:
            raise LLMError("The model produced an empty question.")
        planned = NextQuestion(
            complete=False,
            question=question,
            reason=f"Asked about {described[0]}.",
        )
    except (LLMError, ValueError) as exc:
        # A dead model must not stall intake — fall back to a plain prompt.
        # Whatever was already streamed is left alone: the caller persists and
        # re-renders this return value, so a half-sentence on screen is
        # replaced by the fallback when the turn completes.
        logger.warning("Question planner fell back to a template: %s", exc)
        planned = NextQuestion(
            complete=False,
            question=f"Could you tell me {described[0]}?",
            reason="Fallback question (language model unavailable).",
        )
        if on_token and not question:
            on_token(planned.question)

    # The model does not get to end intake — code owns that.
    planned.complete = False
    planned.missing_fields = outstanding
    # Which field this question is for, so the next turn can tell a denial from
    # a question never asked. Recorded on the message, not inferred later.
    planned.asks_field = field
    return planned
