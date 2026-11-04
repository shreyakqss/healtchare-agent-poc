"""Intake sessions: create, consent, the one-shot identity form, and the streamed clinical
question loop."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import active_intake_out, attachment_out, previous_visit_out, session_out
from app.core.errors import Conflict, DomainError, Unprocessable
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import PatientRegistration
from app.schemas.requests import (
    ConsentRequest,
    IdentityFormRequest,
    MessageRequest,
    ProfileRequest,
    StartSessionRequest,
)
from app.schemas.responses import (
    ActiveIntakeResponse,
    AttachmentResponse,
    LinkedPatientRecord,
    MessageResponse,
    PreviousVisitResponse,
    SessionResponse,
    TurnEvent,
)
from app.security import CurrentPrincipal, case_for_principal, rate_limits, require_roles
from app.services import case_repo, intake_service, prescreen_trigger, visit_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake-sessions", tags=["intake"])
PatientPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("patient"))]


@router.post("", response_model=SessionResponse, status_code=201)
def start_session(payload: StartSessionRequest, principal: PatientPrincipal, db: Session = Depends(get_db)):
    rate_limits.enforce("intake.start", principal.user_id)
    session, case = intake_service.start_session(db, principal.user_id, payload.visit_type, payload.follow_up_of)
    return session_out(db, session, case)


@router.get("/follow-up-options", response_model=list[PreviousVisitResponse])
def follow_up_options(principal: PatientPrincipal, db: Session = Depends(get_db)):
    """This account's own completed visits - what a follow-up visit may be about."""
    return [previous_visit_out(v) for v in visit_history.follow_up_options(db, principal.user_id)]


def _profile_mrn(principal: CurrentPrincipal, db: Session) -> str | None:
    return principal.hms_patient_id or case_repo.last_linked_hms_patient_id(db, principal.user_id)


@router.put("/profile", response_model=LinkedPatientRecord)
def update_profile(payload: ProfileRequest, principal: PatientPrincipal, db: Session = Depends(get_db)):
    """The patient edits their own registration details, written to their own hospital record
    (looked up by this account's MRN, never by a search). Before the first visit's registration
    there is no record to edit - that visit's form creates it."""
    rate_limits.enforce("intake.start", principal.user_id)
    mrn = _profile_mrn(principal, db)
    if not mrn:
        raise Conflict("Your profile is created when you register for your first visit.")
    get_hms().register_patient(mrn, PatientRegistration(
        name=payload.name.strip(), birth_date=payload.birth_date, gender=payload.gender.strip(),
        phone=payload.phone.strip() if payload.phone else None, email=payload.email.strip() if payload.email else None,
        address_line1=payload.address_line1.strip(),
        address_line2=payload.address_line2.strip() if payload.address_line2 else None,
        city=payload.city.strip(), state=payload.state.strip(), postal_code=payload.postal_code.strip(),
        country=payload.country.strip(), contact_preference=payload.contact_preference.strip(),
    ))
    logger.info("Patient profile updated (mrn=%s)", mrn)
    record = linked_record(principal, db)
    if record is None:
        raise Conflict("Your profile was saved but could not be read back. Please reload.")
    return record


@router.get("/greeting")
def greeting(_: PatientPrincipal):
    return {"text": intake_service.GREETING}


@router.get("/past-attachments", response_model=list[AttachmentResponse])
def past_attachments(principal: PatientPrincipal, db: Session = Depends(get_db)):
    """Documents from this account's past visits, fetched eagerly on page load - independent
    of whether this visit even has a session/case yet (identity form not submitted)."""
    return [attachment_out(a) for a in case_repo.attachments_for_owner(db, principal.user_id)]


@router.get("/linked-record", response_model=LinkedPatientRecord | None)
def linked_record(principal: PatientPrincipal, db: Session = Depends(get_db)):
    """Prefill for the identity form when this account is linked to an existing OpenEMR
    patient - either by the Keycloak `hms_patient_id` claim, or (self-registered accounts,
    which carry no such claim) by the account's own most recent prior registration. Read-only
    lookup by MRN either way - never a name/DOB search, so it can only ever return this
    account's own record."""
    mrn = _profile_mrn(principal, db)
    if not mrn:
        return None
    patient = get_hms().get_patient(mrn)
    if patient is None:
        return None
    return LinkedPatientRecord(
        name=patient.name,
        birth_date=patient.birth_date,
        gender=patient.sex,
        phone=patient.phone,
        email=patient.email,
        address_line1=patient.address.line1 if patient.address else None,
        address_line2=patient.address.line2 if patient.address else None,
        city=patient.address.city if patient.address else None,
        state=patient.address.state if patient.address else None,
        postal_code=patient.address.postal_code if patient.address else None,
        country=patient.address.country if patient.address else None,
        contact_preference=patient.contact_preference,
    )


@router.get("/active", response_model=ActiveIntakeResponse)
def get_active_session(principal: PatientPrincipal, db: Session = Depends(get_db)):
    active = intake_service.active_session(db, principal.user_id)
    if active is None:
        return Response(status_code=204)
    return active_intake_out(db, *active)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, principal: PatientPrincipal, db: Session = Depends(get_db)):
    session, case = case_repo.session_or_404(db, session_id)
    case_for_principal(db, case.id, principal, allow_clinician=False)
    return session_out(db, session, case)


@router.post("/{session_id}/consent", response_model=SessionResponse)
def record_consent(
    session_id: uuid.UUID,
    payload: ConsentRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
):
    session, case = case_repo.session_or_404(db, session_id)
    case_for_principal(db, case.id, principal, allow_clinician=False)
    intake_service.record_consent(db, session, case, payload.granted)
    return session_out(db, session, case)


@router.post("/{session_id}/identity", response_model=SessionResponse)
def submit_identity(
    session_id: uuid.UUID,
    payload: IdentityFormRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
):
    """Step 1: who the patient is, submitted at once. 422s if a required identity field
    (per the active hospital config) is still missing afterward."""
    session, case = case_repo.session_or_404(db, session_id)
    case_for_principal(db, case.id, principal, allow_clinician=False)
    intake_service.submit_identity_form(db, session, case, payload)
    missing = case_repo.missing_identity_fields(db, case.id)
    if missing:
        raise Unprocessable("Some required information is still missing - missing fields: " + ", ".join(missing))
    return session_out(db, session, case)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def post_message(
    session_id: uuid.UUID,
    payload: MessageRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
):
    """One turn of the clinical conversation, answered in full (same generator as /stream, drained)."""
    rate_limits.enforce("intake.message", principal.user_id)
    session, case = case_repo.session_or_404(db, session_id)
    case_for_principal(db, case.id, principal, allow_clinician=False)
    async for event in intake_service.process_turn(db, session, case, payload.content):
        if event.type == "done" and event.response is not None:
            if event.response.intake_complete:
                prescreen_trigger.fire_if_ready(db, case.id)
            return event.response
    raise RuntimeError("The intake turn produced no reply.")


@router.post("/{session_id}/messages/stream", response_class=EventSourceResponse)
async def stream_message(
    session_id: uuid.UUID,
    payload: MessageRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
) -> AsyncIterator[TurnEvent]:
    """Same turn as SSE. Failures arrive as a final `error` frame - the 200 is already committed."""
    try:
        rate_limits.enforce("intake.message", principal.user_id)
        session, case = case_repo.session_or_404(db, session_id)
        case_for_principal(db, case.id, principal, allow_clinician=False)
        async for event in intake_service.process_turn(db, session, case, payload.content):
            if event.type == "done" and event.response is not None and event.response.intake_complete:
                prescreen_trigger.fire_if_ready(db, case.id)
            yield event
    except DomainError as exc:
        yield TurnEvent(type="error", status=exc.status_code, detail=exc.detail)
    except Exception as exc:
        logger.error("Intake stream failed (%s)", type(exc).__name__)
        db.rollback()
        yield TurnEvent(type="error", status=500, detail="The assistant could not finish that answer. Please try again.")
