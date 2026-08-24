"""Intake sessions: create, consent, and the streamed question loop."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import session_out
from app.core.errors import DomainError
from app.schemas.requests import ConsentRequest, MessageRequest, QuickStartRequest, StartSessionRequest
from app.schemas.responses import MessageResponse, SessionResponse, TurnEvent
from app.services import case_repo, intake_service, quick_start
from app.workflows import run_prescreen

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake-sessions", tags=["intake"])


def _fire_prescreen(case_id: uuid.UUID) -> None:
    """Kick off pre-screening in the background once intake is complete.

    Not awaited: the patient is waiting on the closing reply, not on rule
    evaluation and an LLM-written briefing. Runs its own db_session, same as
    every other workflow entry point, so it outlives this request either way.
    """

    async def runner() -> None:
        try:
            await run_prescreen(case_id)
        except Exception:
            logger.exception("Background prescreen failed for case %s", case_id)

    asyncio.create_task(runner())


@router.post("", response_model=SessionResponse, status_code=201)
def start_session(payload: StartSessionRequest, db: Session = Depends(get_db)):
    session, case = intake_service.start_session(db, payload)
    return session_out(db, session, case)


@router.get("/greeting")
def greeting():
    return {"text": intake_service.GREETING}


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session, case = case_repo.session_or_404(db, session_id)
    return session_out(db, session, case)


@router.post("/{session_id}/consent", response_model=SessionResponse)
def record_consent(session_id: uuid.UUID, payload: ConsentRequest, db: Session = Depends(get_db)):
    session, case = case_repo.session_or_404(db, session_id)
    intake_service.record_consent(db, session, case, payload.granted)
    return session_out(db, session, case)


@router.post("/quick-start", response_model=SessionResponse, status_code=201)
async def quick_start_session(payload: QuickStartRequest, db: Session = Depends(get_db)):
    """Demo shortcut: fill a whole intake instantly and send it straight to pre-screening.

    Writes the same rows a real conversation ends up with (see quick_start.create), so
    the case that lands in the clinician queue is not distinguishable from a typed one.
    """
    session, case = quick_start.create(db, payload.key)
    _fire_prescreen(case.id)
    return session_out(db, session, case)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def post_message(session_id: uuid.UUID, payload: MessageRequest, db: Session = Depends(get_db)):
    """One turn, answered in full (same generator as /stream, drained)."""
    session, case = case_repo.session_or_404(db, session_id)
    async for event in intake_service.process_turn(db, session, case, payload.content):
        if event.type == "done" and event.response is not None:
            if event.response.intake_complete:
                _fire_prescreen(case.id)
            return event.response
    raise RuntimeError("The intake turn produced no reply.")


@router.post("/{session_id}/messages/stream", response_class=EventSourceResponse)
async def stream_message(session_id: uuid.UUID, payload: MessageRequest, db: Session = Depends(get_db)) -> AsyncIterator[TurnEvent]:
    """Same turn as SSE. Failures arrive as a final `error` frame - the 200 is already committed."""
    try:
        session, case = case_repo.session_or_404(db, session_id)
        async for event in intake_service.process_turn(db, session, case, payload.content):
            if event.type == "done" and event.response is not None and event.response.intake_complete:
                _fire_prescreen(case.id)
            yield event
    except DomainError as exc:
        yield TurnEvent(type="error", status=exc.status_code, detail=exc.detail)
    except Exception:
        logger.exception("Intake stream failed for %s", session_id)
        db.rollback()
        yield TurnEvent(type="error", status=500, detail="The assistant could not finish that answer. Please try again.")