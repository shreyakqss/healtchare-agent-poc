"""Patient intake: session lifecycle, the one-shot identity form, and the adaptive
clinical question loop.

Two steps, in order:
1. `submit_identity_form` - name/age/gender/contact_preference, submitted at once (plain
   form UX, nothing to ask one at a time about).
2. `process_turn` - the clinical fields (reason_for_visit, symptom, duration, history,
   medications, allergies), asked one at a time by the LLM. It is an async generator so
   the reply can be streamed; the `done` frame is the record, the `token` frames are
   transport.

Both steps write through the same session/case rows and the same fact/entry tables; only
the *required field subset* each one is scored against differs (see
app/services/case_repo.py::missing_identity_fields / missing_clinical_fields).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import AgentUnavailable, answer_guard, fact_extractor, patient_assistant, question_planner
from app.agents.question_planner import PlannerContext
from app.agents.schemas import ExtractedFact, ExtractionResult, QuestionResponse
from app.core.config import settings
from app.core.tracing import case_trace
from app.core.errors import Conflict, Forbidden
from app.db import utcnow
from app.domain import intake_fields
from app.domain.demographics import age_from_birth_date
from app.domain.lifecycle import TERMINAL, CaseStatus
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import PatientRegistration
from app.models import (
    AllergyMedication,
    ApplicationUser,
    AuditEvent,
    CaseOwner,
    IntakeMessage,
    IntakeSession,
    PatientCase,
    PatientFact,
)
from app.models.facts import SOURCE_HMS
from app.schemas.requests import IdentityFormRequest
from app.schemas.responses import MessageResponse, TranscriptMessage, TurnEvent
from app.services import assistant_tools, audit, case_repo, hospital_config, lifecycle

logger = logging.getLogger(__name__)

MAX_ASSISTANT_QUESTIONS = 12
MAX_FACT_CHARS = 220

CLOSING = (
    "Thank you - that is everything I need. I am passing your answers to the care team now, "
    "and a clinician will review them before anything else happens."
)
CLOSING_WITH_GAPS = (
    "Thank you - I will pass on what you have told me. Anything still missing will be picked up "
    "by the clinician who reviews your case."
)
GREETING = (
    "Hello, I am the clinic's intake assistant. Tell me what brings you in today, in your own words. "
    "I will ask a few short questions and a clinician will review everything before any decision is made."
)
OUT_OF_SCOPE = "I cannot help with that request because it is outside healthcare, your intake, and this clinic."
RESTRICTED_HEALTHCARE = (
    "I can explain health information and your uploaded reports, but I cannot diagnose you, prescribe or change "
    "treatment or dosage, decide urgency, make bookings or routing decisions, or change your medical record. "
    "I can still explain possible causes in general or help you prepare questions for your clinician."
)
EMERGENCY_GUIDANCE = (
    "I cannot safely assess an emergency in chat. If you may be experiencing a life-threatening emergency, "
    "contact local emergency services now."
)
REFERENCE_UNAVAILABLE = (
    "I cannot answer that reliably because the supporting report or clinic information is not available right now."
)
ASSISTANT_UNAVAILABLE = (
    "I cannot answer that reliably because the healthcare assistant is unavailable right now. Please try again."
)
SAFE_ANSWER_UNAVAILABLE = (
    "I could not provide a safe, reliable answer to that question. Please rephrase it or ask your clinician."
)
UNDERSTANDING_UNAVAILABLE = (
    "I could not process that message because the healthcare assistant is unavailable right now. Please try again."
)


@dataclass(frozen=True)
class TurnExtraction:
    result: ExtractionResult | None
    facts_added: int = 0
    entries_added: int = 0


# --- session ---------------------------------------------------------------

def active_session(db: Session, owner_user_id: uuid.UUID) -> tuple[IntakeSession, PatientCase] | None:
    cutoff = utcnow() - timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES)
    last_message_at = (
        select(func.max(IntakeMessage.created_at))
        .where(IntakeMessage.session_id == IntakeSession.id)
        .correlate(IntakeSession)
        .scalar_subquery()
    )
    last_activity_at = func.coalesce(last_message_at, IntakeSession.started_at, IntakeSession.created_at)
    return (
        db.query(IntakeSession, PatientCase)
        .join(PatientCase, PatientCase.session_id == IntakeSession.id)
        .join(CaseOwner, CaseOwner.case_id == PatientCase.id)
        .filter(
            CaseOwner.user_id == owner_user_id,
            PatientCase.hospital_id == hospital_config.active_id(),
            IntakeSession.status.in_([CaseStatus.CREATED, CaseStatus.INGESTING]),
            last_activity_at >= cutoff,
        )
        .order_by(IntakeSession.created_at.desc())
        .first()
    )


def start_session(db: Session, owner_user_id: uuid.UUID) -> tuple[IntakeSession, PatientCase]:
    owner = db.query(ApplicationUser).filter(ApplicationUser.id == owner_user_id).with_for_update().one()
    active = active_session(db, owner_user_id)
    if active is not None:
        return active
    session = IntakeSession(status=CaseStatus.CREATED, started_at=utcnow(), channel="web")
    db.add(session)
    db.flush()

    case = PatientCase(
        session_id=session.id,
        hms_patient_id=owner.hms_patient_id,
        hospital_id=hospital_config.active_id(),
    )
    db.add(case)
    db.flush()
    db.add(CaseOwner(case_id=case.id, user_id=owner_user_id))

    audit.record(db, case.id, "patient", "intake.session_started", {"channel": "web", "hms_linked": False})
    db.commit()
    return session, case

def record_consent(db: Session, session: IntakeSession, case: PatientCase, granted: bool) -> IntakeSession:
    if session.consent_status != "PENDING":
        raise Conflict(f"Consent has already been recorded as {session.consent_status}.")
    session.consent_status = "GRANTED" if granted else "DECLINED"
    audit.record(db, case.id, "patient", "consent.recorded", {"granted": granted})
    if granted:
        lifecycle.transition(db, session, CaseStatus.INGESTING, "patient", case.id)
    else:
        lifecycle.transition(db, session, CaseStatus.REJECTED, "patient", case.id)
    db.commit()
    return session


def _guard_open(db: Session, session: IntakeSession, case: PatientCase) -> None:
    """Consent granted, session not terminal/closed/expired. Shared by the identity form and the chat turn loop."""
    if session.consent_status != "GRANTED":
        raise Forbidden("Consent must be granted before intake can proceed.")
    if session.status in TERMINAL:
        raise Conflict(f"This session is {session.status.lower()}.")
    if session.status not in {CaseStatus.INGESTING, CaseStatus.CREATED}:
        raise Conflict("Intake is closed for this case - it is already being reviewed.")
    latest_message_at = (
        db.query(IntakeMessage.created_at)
        .filter(IntakeMessage.session_id == session.id)
        .order_by(IntakeMessage.created_at.desc())
        .limit(1)
        .scalar()
    )
    last_activity_at = latest_message_at or session.started_at
    if last_activity_at is not None and utcnow() - last_activity_at > timedelta(minutes=settings.SESSION_TIMEOUT_MINUTES):
        already_audited = (
            db.query(AuditEvent.id)
            .filter(AuditEvent.case_id == case.id, AuditEvent.action == "session.expired")
            .first()
        )
        if not already_audited:
            audit.record(
                db, case.id, "system:session_timeout", "session.expired",
                {"status": session.status, "timeout_minutes": settings.SESSION_TIMEOUT_MINUTES},
            )
            db.commit()
        raise Conflict(
            f"This intake session has been inactive for more than {settings.SESSION_TIMEOUT_MINUTES} minutes "
            "and can no longer accept answers. Please start a new session."
        )


# --- step 1: identity form ---------------------------------------------------------------

def _identity_transcript_text(payload: IdentityFormRequest) -> str:
    return (
        f"Name: {payload.name}\n"
        f"Date of birth: {payload.birth_date.isoformat()}\n"
        f"Gender: {payload.gender}\n"
        f"Phone: {payload.phone or 'Not provided'}\n"
        f"Email: {payload.email or 'Not provided'}\n"
        f"Address: {payload.address_line1}, {payload.city}, {payload.state}, {payload.postal_code}, {payload.country}\n"
        f"Contact preference: {payload.contact_preference}"
    )


def submit_identity_form(db: Session, session: IntakeSession, case: PatientCase, payload: IdentityFormRequest) -> None:
    """Writes the identity fields as facts. Does not raise on an empty required value - the
    caller (api layer) checks case_repo.missing_identity_fields() afterward and 422s the same
    way the old one-shot form did."""
    _guard_open(db, session, case)
    already_submitted = (
        db.query(AuditEvent.id)
        .filter(AuditEvent.case_id == case.id, AuditEvent.action == "intake.identity_submitted")
        .first()
    )
    if already_submitted:
        raise Conflict("Identity details have already been submitted for this intake.")

    # Patient matching happens before this point in the UI. An explicit linked MRN updates
    # that record; otherwise OpenEMR creates one and returns its identifier for this case.
    registered = get_hms().register_patient(
        case.hms_patient_id,
        PatientRegistration(
            name=payload.name.strip(), birth_date=payload.birth_date, gender=payload.gender.strip(),
            phone=payload.phone.strip() if payload.phone else None, email=payload.email.strip() if payload.email else None,
            address_line1=payload.address_line1.strip(), address_line2=payload.address_line2.strip() if payload.address_line2 else None,
            city=payload.city.strip(), state=payload.state.strip(), postal_code=payload.postal_code.strip(),
            country=payload.country.strip(), contact_preference=payload.contact_preference.strip(),
        ),
    )
    case.hms_patient_id = registered.mrn

    turn_index = case_repo.next_turn_index(db, session.id)
    db.add(IntakeMessage(session_id=session.id, role="patient", content=_identity_transcript_text(payload), turn_index=turn_index))

    contact_detail = payload.email if payload.contact_preference == "email" else payload.phone
    contact_preference_value = (
        f"{payload.contact_preference} ({contact_detail.strip()})" if contact_detail else payload.contact_preference
    )
    for kind, value in (
        ("name", payload.name),
        ("age", str(age_from_birth_date(payload.birth_date, utcnow().date()))),
        ("gender", payload.gender),
        ("contact_preference", contact_preference_value),
    ):
        value = value.strip()[:MAX_FACT_CHARS]
        if value:
            db.add(PatientFact(case_id=case.id, kind=kind, value=value, source_turn=turn_index))

    db.commit()

    audit.record(db, case.id, "system:intake", "intake.identity_submitted", {"turn_index": turn_index})
    audit.record(db, case.id, "system:hms_sync", "patient.created_or_updated", {"mrn": registered.mrn})
    db.commit()


# --- step 2: the clinical turn loop -----------------------------------------------------

def _last_asked_question(db: Session, session: IntakeSession) -> IntakeMessage | None:
    return (
        db.query(IntakeMessage)
        .filter(
            IntakeMessage.session_id == session.id,
            IntakeMessage.role == "assistant",
            IntakeMessage.asks_field.isnot(None),
        )
        .order_by(IntakeMessage.turn_index.desc())
        .first()
    )


def _settle_last_question(
    db: Session,
    case: PatientCase,
    asked: IntakeMessage | None,
    response: QuestionResponse | None,
    turn_index: int,
) -> None:
    """Close the previous field only when the turn-understanding result says it was answered."""
    if asked is None or asked.asks_field not in case_repo.missing_clinical_fields(db, case.id):
        return
    value = intake_fields.sentinel_for(response)
    if value is None:
        return
    field = asked.asks_field
    if field in intake_fields.ENTRY_FIELDS:
        db.add(AllergyMedication(case_id=case.id, kind=field, name=value, source_turn=turn_index))
    else:
        db.add(PatientFact(case_id=case.id, kind=field, value=value, source_turn=turn_index))
    db.commit()


def _clinic_term(proposed: str, vocabulary: list[str]) -> str:
    """Keep the label only when it is a term the clinic actually configured.

    A term the model invented would fire a triage rule nobody wrote, so an unrecognised
    one is dropped rather than stored.
    """
    term = proposed.strip().lower()
    return next((known for known in vocabulary if known.lower() == term), "")


async def _extract_and_store(
    db: Session,
    case: PatientCase,
    message: str,
    turn_index: int,
    is_opening: bool,
    asked: IntakeMessage | None,
    transcript: list[dict[str, str]],
) -> TurnExtraction:
    """`is_opening` is true for the patient's first CLINICAL statement - not necessarily
    turn_index 0, since the identity form now takes turn_index 0. It is computed from
    whether any assistant question has been asked yet, not from the raw index."""
    vocabulary = hospital_config.clinic_vocabulary()
    try:
        result = await fact_extractor.extract(
            message,
            asked.asks_field if asked else None,
            asked.content if asked else None,
            transcript,
            vocabulary,
        )
    except AgentUnavailable as exc:
        logger.warning("Extraction unavailable on turn %s (%s)", turn_index, type(exc).__name__)
        return TurnExtraction(result=None)

    existing = {(f.kind, f.value.strip().lower()) for f in case_repo.facts(db, case.id)}
    existing_entries = {(e.kind, e.name.strip().lower()) for e in case_repo.entries(db, case.id)}
    facts = list(result.facts)

    # A reported opening symptom is also the reason for seeking care; unrelated text is never promoted.
    if (
        is_opening
        and not any(f.kind == "reason_for_visit" for f in facts)
        and not any(k == "reason_for_visit" for k, _ in existing)
    ):
        symptom = next((fact for fact in facts if fact.kind == "symptom"), None)
        if symptom:
            facts.insert(0, ExtractedFact(
                kind="reason_for_visit", value=symptom.value, normalized=symptom.normalized, confidence=symptom.confidence,
            ))
    # reason_for_visit is not capped to one entry: a later, distinct statement is treated as a
    # correction - PatientFact rows stay append-only, but callers show the latest one per kind
    # (see case_repo.captured_fields), so a correction is what the patient and the record see.
    added = 0
    for fact in facts:
        value = fact.value.strip()[:MAX_FACT_CHARS]
        if not value or (fact.kind, value.lower()) in existing:
            continue
        db.add(PatientFact(
            case_id=case.id, kind=fact.kind, value=value, normalized=_clinic_term(fact.normalized, vocabulary),
            source_turn=turn_index, confidence=fact.confidence,
        ))
        existing.add((fact.kind, value.lower()))
        added += 1

    added_entries = 0
    for entry in result.allergies_medications:
        name = entry.name.strip()
        if not name or (entry.kind, name.lower()) in existing_entries:
            continue
        db.add(AllergyMedication(case_id=case.id, kind=entry.kind, name=name, reaction_or_dose=entry.reaction_or_dose.strip() or None, source_turn=turn_index))
        existing_entries.add((entry.kind, name.lower()))
        added_entries += 1

    db.commit()
    return TurnExtraction(result=result, facts_added=added, entries_added=added_entries)


def _on_file(db: Session, case_id: uuid.UUID) -> list[str]:
    lines = [f"{f.kind}: {f.value}" + (" (hospital record)" if f.source == SOURCE_HMS else "") for f in case_repo.facts(db, case_id)]
    lines += [f"{e.kind}: {e.name}" + (" (hospital record)" if e.source == SOURCE_HMS else "") for e in case_repo.entries(db, case_id)]
    return lines


def _transcript(db: Session, session_id: uuid.UUID) -> list[TranscriptMessage]:
    return [TranscriptMessage(role=m.role, content=m.content, turn_index=m.turn_index) for m in case_repo.messages(db, session_id)]


async def _streamed(run: Callable[[Callable[[str], None]], Awaitable[str]]) -> AsyncIterator[tuple[str, str]]:
    """Forward agent tokens, then yield its complete text."""
    tokens: asyncio.Queue[str | None] = asyncio.Queue()
    task = asyncio.create_task(run(tokens.put_nowait))
    task.add_done_callback(lambda _: tokens.put_nowait(None))
    try:
        while (chunk := await tokens.get()) is not None:
            yield "token", chunk
        yield "text", await task
    except BaseException:
        task.cancel()
        raise


def _clinical_transcript(db: Session, session_id: uuid.UUID) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in case_repo.messages(db, session_id)
        if message.turn_index > 0
    ]


def _bounded_reply(text: str, asks_field: str | None, outstanding: list[str]) -> str:
    if asks_field:
        ctx = PlannerContext(field=asks_field, outstanding=outstanding, transcript=[])
        return f"{text} {question_planner.fallback_question(ctx)}"
    closing = CLOSING if not outstanding else CLOSING_WITH_GAPS
    return f"{text} {closing}"


async def _answer_patient_question(
    db: Session,
    session: IntakeSession,
    case: PatientCase,
    extraction: ExtractionResult,
    asks_field: str | None,
    outstanding: list[str],
    complete: bool,
) -> tuple[str, str]:
    scope = extraction.question_scope
    if scope == "out_of_scope":
        return _bounded_reply(OUT_OF_SCOPE, asks_field, outstanding), "scope"
    if scope == "restricted_healthcare":
        return _bounded_reply(RESTRICTED_HEALTHCARE, asks_field, outstanding), "scope"
    if scope == "urgent_safety":
        return _bounded_reply(EMERGENCY_GUIDANCE, asks_field, outstanding), "safety"
    if scope not in {"personal_record", "clinic", "general_health"}:
        return _bounded_reply(UNDERSTANDING_UNAVAILABLE, asks_field, outstanding), "scope"

    reference = await assistant_tools.resolve(db, case.id, scope, extraction.health_topic)
    if reference is None:
        return _bounded_reply(REFERENCE_UNAVAILABLE, asks_field, outstanding), "unavailable"

    question = extraction.patient_question or ""
    asks_for = intake_fields.FIELD_PROMPTS.get(asks_field, asks_field) if asks_field else None
    transcript = _clinical_transcript(db, session.id)
    try:
        reply = await patient_assistant.answer(question, reference, transcript, asks_for)
        review = await answer_guard.check(scope, question, reference, reply)
    except AgentUnavailable as exc:
        logger.warning("Patient answer unavailable (%s)", type(exc).__name__)
        return _bounded_reply(ASSISTANT_UNAVAILABLE, asks_field, outstanding), "fallback"

    if review.decision == "block":
        return _bounded_reply(SAFE_ANSWER_UNAVAILABLE, asks_field, outstanding), "guard"
    if complete:
        closing = CLOSING if not outstanding else CLOSING_WITH_GAPS
        reply = f"{reply} {closing}"
    return reply, f"assistant:{scope}"


async def process_turn(db: Session, session: IntakeSession, case: PatientCase, content: str) -> AsyncIterator[TurnEvent]:
    """Every agent run of one turn under a single trace; the turn itself is `_process_turn`."""
    with case_trace("intake.turn", case.id):
        async for event in _process_turn(db, session, case, content):
            yield event


async def _process_turn(db: Session, session: IntakeSession, case: PatientCase, content: str) -> AsyncIterator[TurnEvent]:
    """One turn of the clinical conversation. Requires the identity form to already be
    submitted - not enforced here (that would need an extra query on every turn); the caller
    only opens the chat UI once the identity step reports nothing missing."""
    _guard_open(db, session, case)
    missing_identity = case_repo.missing_identity_fields(db, case.id)
    if missing_identity:
        raise Conflict(f"Complete the identity form before clinical intake ({', '.join(missing_identity)} missing).")

    started = time.perf_counter()
    asked = _last_asked_question(db, session)
    is_opening = asked is None
    turn_index = case_repo.next_turn_index(db, session.id)
    transcript = _clinical_transcript(db, session.id)
    db.add(IntakeMessage(session_id=session.id, role="patient", content=content, turn_index=turn_index))
    db.commit()

    turn = await _extract_and_store(db, case, content, turn_index, is_opening, asked, transcript)
    extraction = turn.result
    question = extraction.patient_question if extraction else None
    _settle_last_question(
        db,
        case,
        asked,
        extraction.current_question_response if extraction else None,
        turn_index,
    )

    outstanding = case_repo.missing_clinical_fields(db, case.id)
    asked_so_far = sum(
        1 for m in case_repo.messages(db, session.id) if m.role == "assistant" and m.asks_field is not None
    )
    asks_field: str | None = None
    planner_mode = "code"
    reply_streamed = False

    if extraction is None:
        reply, complete, planner_mode = UNDERSTANDING_UNAVAILABLE, False, "fallback"
        yield TurnEvent(type="token", text=reply)
        reply_streamed = True
    elif question:
        complete = not outstanding or asked_so_far >= MAX_ASSISTANT_QUESTIONS
        asks_field = None if complete else outstanding[0]
        reply, planner_mode = await _answer_patient_question(
            db, session, case, extraction, asks_field, outstanding, complete
        )
        yield TurnEvent(type="token", text=reply)
        reply_streamed = True
    else:
        # A pending prescription's candidates are asked about once, even for a hospital config
        # that does not require the `medication` field and even after an earlier prescription's
        # candidates were already answered - independent of the required-field loop below.
        pending_meds = case_repo.pending_medication_candidates(db, case.id)
        force_medication = bool(pending_meds) and "medication" not in outstanding
        if not outstanding and not force_medication:
            reply, complete = CLOSING, True
        elif asked_so_far >= MAX_ASSISTANT_QUESTIONS:
            reply, complete = CLOSING_WITH_GAPS, True
        else:
            asks_field = "medication" if force_medication else outstanding[0]
            complete = False
            if asks_field == "medication" and pending_meds:
                # Mark every attachment's candidates as surfaced now that the confirm
                # question is actually about to be asked, so it isn't asked again.
                for a in case_repo.attachments(db, case.id):
                    if a.extracted_medications and not a.medication_candidates_confirmed:
                        a.medication_candidates_confirmed = True
            ctx = PlannerContext(
                field=asks_field,
                outstanding=outstanding,
                transcript=case_repo.transcript(db, session.id),
                on_file=_on_file(db, case.id),
                patient_name=case_repo.demographics(db, case.id).get("name"),
                medication_candidates=pending_meds if asks_field == "medication" else [],
            )
            try:
                async for kind, text in _streamed(lambda emit: question_planner.plan(ctx, emit)):
                    if kind == "token":
                        reply_streamed = True
                        yield TurnEvent(type="token", text=text)
                    else:
                        reply, planner_mode = text, "llm"
            except AgentUnavailable as exc:
                # Whatever was streamed is replaced client-side by the `done` frame.
                logger.warning("Planner unavailable (%s)", type(exc).__name__)
                reply = question_planner.fallback_question(ctx)
                planner_mode = "fallback"
                yield TurnEvent(type="token", text=reply)
                reply_streamed = True

    if complete and not reply_streamed:
        yield TurnEvent(type="token", text=reply)

    db.add(IntakeMessage(session_id=session.id, role="assistant", content=reply, turn_index=turn_index + 1, asks_field=asks_field))
    audit.record(
        db, case.id, "system:intake", "intake.turn_processed",
        {
            "turn_index": turn_index,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "extraction": {
                "facts": turn.facts_added,
                "entries": turn.entries_added,
                "mode": "llm" if extraction else "fallback",
                "response": extraction.current_question_response if extraction else None,
                "has_question": bool(question),
                "question_scope": extraction.question_scope if extraction else None,
            },
            "planner": planner_mode,
            "asks_field": asks_field,
            "intake_complete": complete,
        },
    )
    db.commit()

    yield TurnEvent(
        type="done",
        response=MessageResponse(
            session_id=str(session.id),
            case_id=str(case.id),
            turn_index=turn_index,
            reply=reply,
            asks_field=asks_field,
            missing_fields=outstanding,
            intake_complete=complete,
            transcript=_transcript(db, session.id),
            captured_fields=case_repo.captured_fields(db, case.id),
        ),
    )
