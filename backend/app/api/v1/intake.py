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
from app.api.v1.serializers import active_intake_out, session_out
from app.core.errors import DomainError, Unprocessable
from app.schemas.requests import ConsentRequest, IdentityFormRequest, MessageRequest, StartSessionRequest
from app.schemas.responses import ActiveIntakeResponse, MessageResponse, SessionResponse, TurnEvent
from app.security import CurrentPrincipal, case_for_principal, rate_limits, require_roles
from app.services import case_repo, intake_service, prescreen_trigger

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake-sessions", tags=["intake"])
PatientPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("patient"))]


@router.post("", response_model=SessionResponse, status_code=201)
def start_session(payload: StartSessionRequest, principal: PatientPrincipal, db: Session = Depends(get_db)):
    rate_limits.enforce("intake.start", principal.user_id)
    session, case = intake_service.start_session(db, principal.user_id)
    return session_out(db, session, case)


@router.get("/greeting")
def greeting(_: PatientPrincipal):
    return {"text": intake_service.GREETING}


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
