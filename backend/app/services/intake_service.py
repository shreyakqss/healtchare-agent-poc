"""Patient intake: session lifecycle and the adaptive question loop.

`process_turn` is the only path a patient statement takes into the system. It
is an async generator so the reply can be streamed; the `done` frame is the
record, the `token` frames are transport.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.agents import AgentUnavailable, fact_extractor, question_planner
from app.agents.question_planner import PlannerContext
from app.agents.schemas import ExtractedFact
from app.core.errors import Conflict, Forbidden, NotFound
from app.db import utcnow
from app.domain import intake_fields
from app.domain.intake_fields import PLACEHOLDERS
from app.domain.lifecycle import TERMINAL, CaseStatus
from app.integrations.hms import get_hms
from app.models import AllergyMedication, IntakeMessage, IntakeSession, PatientCase, PatientFact
from app.models.facts import NO_TURN, SOURCE_HMS
from app.schemas.requests import StartSessionRequest
from app.schemas.responses import MessageResponse, TranscriptMessage, TurnEvent
from app.services import audit, case_repo, hospital_config, lifecycle

logger = logging.getLogger(__name__)

MAX_ASSISTANT_QUESTIONS = 12
MAX_FACT_CHARS = 220
DEMOGRAPHIC_KEYS = {"name": "name", "age": "age", "gender": "sex"}

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


# --- session ---------------------------------------------------------------

def start_session(db: Session, payload: StartSessionRequest) -> tuple[IntakeSession, PatientCase]:
    session = IntakeSession(status=CaseStatus.CREATED, started_at=utcnow(), channel=payload.channel)
    db.add(session)
    db.flush()

    demographics = dict(payload.demographics)
    hms_patient = get_hms().get_patient(payload.mrn) if payload.mrn else None
    if payload.mrn and hms_patient is None:
        raise NotFound(f"No HMS patient with MRN {payload.mrn}.")
    if hms_patient:
        demographics.update({"name": hms_patient.name, "age": str(hms_patient.age), "sex": hms_patient.sex, "mrn": hms_patient.mrn})

    case = PatientCase(
        session_id=session.id,
        demographics=demographics,
        hms_patient_id=hms_patient.mrn if hms_patient else None,
        hospital_id=hospital_config.active_id(),
    )
    db.add(case)
    db.flush()

    audit.record(db, case.id, "patient", "intake.session_started", {"channel": payload.channel, "hms_linked": bool(hms_patient)})
    if hms_patient:
        _import_hms_record(db, case, hms_patient)
    db.commit()
    return session, case


def _import_hms_record(db: Session, case: PatientCase, patient) -> None:
    """Copy what the hospital already knows, tagged `source=hms` so it is never mistaken for a patient statement."""
    for kind, value in (("name", patient.name), ("age", str(patient.age)), ("gender", patient.sex)):
        db.add(PatientFact(case_id=case.id, kind=kind, value=value, source=SOURCE_HMS, source_turn=NO_TURN))
    for condition in patient.conditions:
        db.add(PatientFact(case_id=case.id, kind="history", value=condition, source=SOURCE_HMS, source_turn=NO_TURN))
    for med in patient.medications:
        db.add(AllergyMedication(case_id=case.id, kind="medication", name=med, source=SOURCE_HMS, source_turn=NO_TURN))
    for allergy in patient.allergies:
        db.add(AllergyMedication(case_id=case.id, kind="allergy", name=allergy, source=SOURCE_HMS, source_turn=NO_TURN))
    audit.record(
        db, case.id, "system:hms", "hms.record_linked",
        {"mrn": patient.mrn, "conditions": len(patient.conditions), "medications": len(patient.medications), "allergies": len(patient.allergies)},
    )


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


# --- the turn --------------------------------------------------------------

def _settle_last_question(db: Session, case: PatientCase, session: IntakeSession) -> None:
    """Close the field the previous question asked about if the answer produced no fact."""
    asked = (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session.id, IntakeMessage.role == "assistant", IntakeMessage.asks_field.isnot(None))
        .order_by(IntakeMessage.turn_index.desc())
        .first()
    )
    if asked is None:
        return
    reply = (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session.id, IntakeMessage.role == "patient", IntakeMessage.turn_index > asked.turn_index)
        .order_by(IntakeMessage.turn_index)
        .first()
    )
    if reply is None or asked.asks_field not in case_repo.missing_fields(db, case.id):
        return
    value = intake_fields.settle_value(reply.content)
    field = asked.asks_field
    if field in intake_fields.ENTRY_FIELDS:
        db.add(AllergyMedication(case_id=case.id, kind=field, name=value, source_turn=reply.turn_index))
    else:
        db.add(PatientFact(case_id=case.id, kind=field, value=value, source_turn=reply.turn_index))
    db.commit()


async def _extract_and_store(db: Session, case: PatientCase, message: str, turn_index: int) -> dict[str, int]:
    try:
        result = await fact_extractor.extract(message)
    except AgentUnavailable as exc:
        # Losing structure is bad; losing the statement is worse. Keep the raw text.
        logger.warning("Extraction unavailable on turn %s: %s", turn_index, exc)
        if intake_fields.is_empty_answer(message) or intake_fields.is_denial(message):
            return {"facts": 0, "entries": 0, "mode": "fallback"}  # settled by the next turn
        kind = "reason_for_visit" if turn_index == 0 else "symptom"
        db.add(PatientFact(case_id=case.id, kind=kind, value=message.strip()[:MAX_FACT_CHARS], source_turn=turn_index, confidence=0.3))
        db.commit()
        return {"facts": 1, "entries": 0, "mode": "fallback"}

    existing = {(f.kind, f.value.strip().lower()) for f in case_repo.facts(db, case.id)}
    existing_entries = {(e.kind, e.name.strip().lower()) for e in case_repo.entries(db, case.id)}
    facts = list(result.facts)

    # The opening statement *is* the reason for the visit, whatever the model tagged it as.
    if turn_index == 0 and not any(f.kind == "reason_for_visit" for f in facts) and not any(k == "reason_for_visit" for k, _ in existing):
        facts.insert(0, ExtractedFact(kind="reason_for_visit", value=message.strip()[:MAX_FACT_CHARS], confidence=0.9))
    has_reason = any(k == "reason_for_visit" for k, _ in existing)

    added = 0
    for fact in facts:
        value = fact.value.strip()[:MAX_FACT_CHARS]
        if not value or intake_fields.is_empty_answer(value) or (fact.kind, value.lower()) in existing:
            continue
        if fact.kind == "reason_for_visit":
            if has_reason:
                continue
            has_reason = True
        db.add(PatientFact(case_id=case.id, kind=fact.kind, value=value, source_turn=turn_index, confidence=fact.confidence))
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
    if added:
        _sync_demographics(db, case)
    return {"facts": added, "entries": added_entries, "mode": "llm"}


def _sync_demographics(db: Session, case: PatientCase) -> None:
    """Copy name/age/gender facts onto the case header. First value stated wins."""
    merged = dict(case.demographics or {})
    for f in case_repo.facts(db, case.id):
        if f.kind in DEMOGRAPHIC_KEYS and f.value not in PLACEHOLDERS:
            merged.setdefault(DEMOGRAPHIC_KEYS[f.kind], f.value.strip())
    if merged != case.demographics:
        case.demographics = merged  # reassigned: SQLAlchemy does not track in-place JSON edits
        db.commit()


def _on_file(db: Session, case_id: uuid.UUID) -> list[str]:
    lines = [f"{f.kind}: {f.value}" + (" (hospital record)" if f.source == SOURCE_HMS else "") for f in case_repo.facts(db, case_id)]
    lines += [f"{e.kind}: {e.name}" + (" (hospital record)" if e.source == SOURCE_HMS else "") for e in case_repo.entries(db, case_id)]
    return lines


def _transcript(db: Session, session_id: uuid.UUID) -> list[TranscriptMessage]:
    return [TranscriptMessage(role=m.role, content=m.content, turn_index=m.turn_index) for m in case_repo.messages(db, session_id)]


async def process_turn(db: Session, session: IntakeSession, case: PatientCase, content: str) -> AsyncIterator[TurnEvent]:
    if session.consent_status != "GRANTED":
        raise Forbidden("Consent must be granted before intake can proceed.")
    if session.status in TERMINAL:
        raise Conflict(f"This session is {session.status.lower()}.")
    if session.status not in {CaseStatus.INGESTING, CaseStatus.CREATED}:
        raise Conflict("Intake is closed for this case - it is already being reviewed.")

    started = time.perf_counter()
    turn_index = case_repo.next_turn_index(db, session.id)
    db.add(IntakeMessage(session_id=session.id, role="patient", content=content, turn_index=turn_index))
    db.commit()

    _settle_last_question(db, case, session)
    extraction = await _extract_and_store(db, case, content, turn_index)

    outstanding = case_repo.missing_fields(db, case.id)
    asked_so_far = sum(1 for m in case_repo.messages(db, session.id) if m.role == "assistant")
    asks_field: str | None = None
    planner_mode = "code"

    if not outstanding:
        reply, complete = CLOSING, True
    elif asked_so_far >= MAX_ASSISTANT_QUESTIONS:
        reply, complete = CLOSING_WITH_GAPS, True
    else:
        asks_field, complete = outstanding[0], False
        ctx = PlannerContext(
            field=asks_field,
            outstanding=outstanding,
            transcript=case_repo.transcript(db, session.id),
            on_file=_on_file(db, case.id),
            patient_name=(case.demographics or {}).get("name"),
        )
        # The planner runs as a task so its tokens can be forwarded while it is still writing.
        tokens: asyncio.Queue[str | None] = asyncio.Queue()
        task = asyncio.create_task(question_planner.plan(ctx, tokens.put_nowait))
        task.add_done_callback(lambda _: tokens.put_nowait(None))
        try:
            while (chunk := await tokens.get()) is not None:
                yield TurnEvent(type="token", text=chunk)
            reply = await task
            planner_mode = "llm"
        except AgentUnavailable as exc:
            # Whatever was streamed is replaced client-side by the `done` frame.
            logger.warning("Planner unavailable: %s", exc)
            reply = question_planner.fallback_question(ctx)
            planner_mode = "fallback"
            yield TurnEvent(type="token", text=reply)
        except BaseException:
            task.cancel()
            raise

    if complete:
        yield TurnEvent(type="token", text=reply)

    db.add(IntakeMessage(session_id=session.id, role="assistant", content=reply, turn_index=turn_index + 1, asks_field=asks_field))
    audit.record(
        db, case.id, "system:intake", "intake.turn_processed",
        {
            "turn_index": turn_index,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "extraction": extraction,
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
        ),
    )