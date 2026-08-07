"""Question Planner — decides the single next intake question.

Uses the LLM, but the *stopping condition* is computed in code: the required
field list comes from hospital.yaml and is checked against facts already in the
database. The model chooses phrasing; it does not get to decide that intake is
finished.
"""
import logging
from sqlalchemy.orm import Session

from models import AllergyMedication, PatientFact
from schemas.agent_outputs import NextQuestion, json_schema
from services import hospital_config
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

# Hard ceiling on follow-ups. A model that keeps failing to extract a field
# would otherwise ask about it forever with no way for the patient to finish.
# Stopping and routing the gap to a clinician is the documented behaviour:
# missing information belongs in human review, not in an unescapable loop.
MAX_ASSISTANT_QUESTIONS = 12

SYSTEM = """You are the intake assistant for a medical clinic, talking to a patient.

Ask exactly ONE short, plain-language question at a time to collect the missing \
information listed by the caller. Be warm and brief.

Hard rules:
- Never diagnose, never suggest treatment, never interpret test results.
- Never tell the patient how urgent their case is.
- If the patient describes a life-threatening emergency, your question must be to \
tell them to contact emergency services immediately.
- Ask only about the missing fields you are given."""

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


async def plan_next_question(db: Session, case_id, transcript: list[dict]) -> NextQuestion:
    """Return the next question, or `complete=True` when nothing is outstanding."""
    outstanding = missing_fields(db, case_id)

    if not outstanding:
        return NextQuestion(
            complete=True,
            question="",
            missing_fields=[],
            reason="All required intake fields have been collected.",
        )

    asked = sum(1 for turn in transcript if turn.get("role") == "assistant")
    if asked >= MAX_ASSISTANT_QUESTIONS:
        return NextQuestion(
            complete=True,
            question="",
            missing_fields=outstanding,
            reason=(
                f"Stopped after {asked} questions with "
                f"{len(outstanding)} field(s) still outstanding. The gaps are "
                f"recorded as missing information for the clinician."
            ),
        )

    described = [FIELD_PROMPTS.get(f, f) for f in outstanding]
    history = "\n".join(f"{m['role']}: {m['content']}" for m in transcript[-8:])

    user = (
        f"Conversation so far:\n{history or '(nothing yet)'}\n\n"
        f"Still missing: {', '.join(described)}.\n\n"
        f"Ask one question about: {described[0]}."
    )

    try:
        raw = await llm.chat_json(SYSTEM, user, json_schema(NextQuestion))
        planned = NextQuestion.model_validate(raw)
    except (LLMError, ValueError) as exc:
        # A dead model must not stall intake — fall back to a plain prompt.
        logger.warning("Question planner fell back to a template: %s", exc)
        planned = NextQuestion(
            complete=False,
            question=f"Could you tell me {described[0]}?",
            reason="Fallback question (language model unavailable).",
        )

    # The model does not get to end intake — code owns that.
    planned.complete = False
    planned.missing_fields = outstanding
    if not planned.question.strip():
        planned.question = f"Could you tell me {described[0]}?"
    return planned
