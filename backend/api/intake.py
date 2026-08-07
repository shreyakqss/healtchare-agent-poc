"""Patient intake: session creation, consent, and the adaptive question loop."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents import intake_agent
from agents.question_planner import missing_fields
from models import IntakeMessage, IntakeSession, PatientCase, get_db
from schemas.request import ConsentRequest, MessageRequest, StartSessionRequest
from schemas.response import MessageResponse, SessionResponse
from workflow.graph import intake_graph, run_config

router = APIRouter(prefix="/intake-sessions", tags=["intake"])


def _load(db: Session, session_id: uuid.UUID) -> tuple[IntakeSession, PatientCase]:
    session = db.get(IntakeSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")
    case = db.query(PatientCase).filter(PatientCase.session_id == session.id).first()
    if case is None:
        raise HTTPException(status_code=404, detail="Patient case not found.")
    return session, case


def _transcript(db: Session, session_id: uuid.UUID) -> list[dict[str, str]]:
    messages = (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session_id)
        .order_by(IntakeMessage.turn_index)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in messages]


@router.post("", response_model=SessionResponse, status_code=201)
def start_session(payload: StartSessionRequest, db: Session = Depends(get_db)):
    session, case = intake_agent.start_session(db, payload.demographics)
    return SessionResponse(
        session_id=str(session.id),
        case_id=str(case.id),
        status=session.status,
        consent_status=session.consent_status,
    )


@router.post("/{session_id}/consent", response_model=SessionResponse)
def record_consent(
    session_id: uuid.UUID, payload: ConsentRequest, db: Session = Depends(get_db)
):
    session, case = _load(db, session_id)
    if session.consent_status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Consent has already been recorded as {session.consent_status}.",
        )

    session = intake_agent.record_consent(db, session, case.id, payload.granted)
    return SessionResponse(
        session_id=str(session.id),
        case_id=str(case.id),
        status=session.status,
        consent_status=session.consent_status,
    )


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session, case = _load(db, session_id)
    return SessionResponse(
        session_id=str(session.id),
        case_id=str(case.id),
        status=session.status,
        consent_status=session.consent_status,
    )


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def post_message(
    session_id: uuid.UUID, payload: MessageRequest, db: Session = Depends(get_db)
):
    """One patient turn: store it, extract facts, return the next question.

    Consent is enforced here rather than in the graph — no patient information
    is processed before it has been granted.
    """
    session, case = _load(db, session_id)

    if session.consent_status != "GRANTED":
        raise HTTPException(
            status_code=403,
            detail="Consent must be granted before intake can proceed.",
        )
    if session.status in {"COMPLETED", "REJECTED"}:
        raise HTTPException(
            status_code=409, detail=f"This session is {session.status.lower()}."
        )

    turn_index = (
        db.query(IntakeMessage).filter(IntakeMessage.session_id == session.id).count()
    )
    db.add(
        IntakeMessage(
            session_id=session.id,
            role="patient",
            content=payload.content,
            turn_index=turn_index,
        )
    )
    db.commit()

    state = await intake_graph.ainvoke(
        {
            "session_id": str(session.id),
            "case_id": str(case.id),
            "last_message": payload.content,
            "turn_index": turn_index,
            "transcript": _transcript(db, session.id),
        },
        config=run_config(db),
    )

    next_question = state.get("next_question", "")
    intake_complete = bool(state.get("intake_complete"))

    if next_question:
        db.add(
            IntakeMessage(
                session_id=session.id,
                role="assistant",
                content=next_question,
                turn_index=turn_index + 1,
            )
        )
        db.commit()

    return MessageResponse(
        session_id=str(session.id),
        case_id=str(case.id),
        turn_index=turn_index,
        next_question=next_question,
        missing_fields=state.get("missing_fields", missing_fields(db, case.id)),
        intake_complete=intake_complete,
        transcript=_transcript(db, session.id),
    )
