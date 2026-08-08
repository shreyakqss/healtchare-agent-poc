"""Patient intake: session creation, consent, and the adaptive question loop."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse
from sqlalchemy.orm import Session

from agents import intake_agent
from agents.question_planner import missing_fields
from models import AuditEvent, IntakeMessage, IntakeSession, PatientCase, get_db
from schemas.request import ConsentRequest, MessageRequest, StartSessionRequest
from schemas.response import MessageResponse, SessionResponse, TurnEvent
from services.voice import split_for_speech
from workflow.graph import intake_graph, run_config

logger = logging.getLogger(__name__)

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


async def process_turn(
    db: Session,
    session: IntakeSession,
    case: PatientCase,
    content: str,
    channel: str = "text",
) -> AsyncIterator[TurnEvent]:
    """One patient turn: store it, run the intake graph, emit the next question.

    **The only path a patient statement takes into the workflow.** The voice
    endpoints transcribe audio and then call this, so a spoken turn and a typed
    turn are the same turn — `channel` is recorded for observability and
    changes no behaviour. Anything that needs to reach the agents belongs here,
    not beside here.

    It is a generator so that the reply can be watched as it is written, but it
    is not two pipelines: the graph runs exactly once and produces exactly one
    reply. `token` frames are that reply arriving, `segment` frames are the
    same text cut for speech, and `done` carries the canonical turn — the
    chunks are transport, the `done` frame is the record. A caller that wants
    the old behaviour drains to `done` and ignores the rest.

    Consent is enforced at this level rather than in the graph — no patient
    information is processed before it has been granted.
    """
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
            content=content,
            turn_index=turn_index,
        )
    )
    db.commit()

    # The graph runs as a task so its tokens can be read while it is still
    # running; the queue is this turn's alone, which is all "sessions stream
    # independently" needs to mean when nothing is shared in the first place.
    tokens: asyncio.Queue[str | None] = asyncio.Queue()
    started = time.perf_counter()
    run = asyncio.create_task(
        intake_graph.ainvoke(
            {
                "session_id": str(session.id),
                "case_id": str(case.id),
                "last_message": content,
                "turn_index": turn_index,
                "transcript": _transcript(db, session.id),
            },
            config=run_config(db, tokens.put_nowait),
        )
    )
    run.add_done_callback(lambda _: tokens.put_nowait(None))

    streamed = ""
    pending = ""  # accumulated but not yet long enough to be worth speaking
    segments = 0
    chunks = 0
    ttft_ms: float | None = None

    try:
        while (chunk := await tokens.get()) is not None:
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - started) * 1000
            chunks += 1
            streamed += chunk
            yield TurnEvent(type="token", text=chunk)

            ready, pending = split_for_speech(pending + chunk)
            for phrase in ready:
                yield TurnEvent(type="segment", index=segments, text=phrase)
                segments += 1

        state = await run
    except BaseException:
        # Includes the client hanging up, which closes this generator. Leaving
        # the graph running would mean writing to a session the caller is about
        # to close; the patient's own message is already committed, so the
        # worst case is an unanswered turn they can simply send again.
        run.cancel()
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000

    tail, _ = split_for_speech(pending, final=True)
    for phrase in tail:
        yield TurnEvent(type="segment", index=segments, text=phrase)
        segments += 1

    next_question = state.get("next_question", "")
    intake_complete = bool(state.get("intake_complete"))

    # The canonical record is the whole reply, written once — never the chunks.
    # It is what the model returned, which is not always what was streamed: a
    # mid-stream failure falls back to a template, and this is the version that
    # both the transcript and the `done` frame carry.
    if next_question:
        db.add(
            IntakeMessage(
                session_id=session.id,
                role="assistant",
                content=next_question,
                turn_index=turn_index + 1,
                # Empty on the closing message — it asks for nothing.
                asks_field=state.get("asks_field") or None,
            )
        )

    # The extractor and planner write no audit row of their own, so this is the
    # only record of how long a turn took. Both channels get it.
    db.add(
        AuditEvent(
            case_id=case.id,
            actor="system:intake_graph",
            action="intake.turn_processed",
            payload={
                "channel": channel,
                "turn_index": turn_index,
                "duration_ms": round(elapsed_ms, 1),
                "characters": len(content),
                "intake_complete": intake_complete,
                "status": "ok",
            },
        )
    )
    # Generation timings, which the turn event above cannot carry because it
    # measures the whole graph. `ttft_ms` runs from the start of the turn, so
    # it includes fact extraction — that is the wait the patient actually sits
    # through, and splitting it would need timing the extractor separately.
    db.add(
        AuditEvent(
            case_id=case.id,
            actor="system:question_planner",
            action="llm.response_streamed",
            payload={
                "channel": channel,
                "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                "generation_ms": (
                    round(elapsed_ms - ttft_ms, 1) if ttft_ms is not None else None
                ),
                "duration_ms": round(elapsed_ms, 1),
                "chunks": chunks,
                "characters": len(streamed),
                "speech_segments": segments,
                "turn_index": turn_index,
                "status": "ok" if streamed else "empty",
            },
        )
    )
    db.commit()

    yield TurnEvent(
        type="done",
        response=MessageResponse(
            session_id=str(session.id),
            case_id=str(case.id),
            turn_index=turn_index,
            next_question=next_question,
            missing_fields=state.get("missing_fields", missing_fields(db, case.id)),
            intake_complete=intake_complete,
            transcript=_transcript(db, session.id),
        ),
    )


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def post_message(
    session_id: uuid.UUID, payload: MessageRequest, db: Session = Depends(get_db)
):
    """One patient turn, answered in full.

    The same generator `/messages/stream` serves, drained to its end — kept for
    callers that have no use for a stream: the tests, and the future patient
    simulator.
    """
    session, case = _load(db, session_id)
    async for event in process_turn(
        db, session, case, payload.content, channel=payload.channel
    ):
        if event.type == "done" and event.response is not None:
            return event.response
    raise HTTPException(status_code=500, detail="The intake turn produced no reply.")


@router.post("/{session_id}/messages/stream", response_class=EventSourceResponse)
async def stream_message(
    session_id: uuid.UUID, payload: MessageRequest, db: Session = Depends(get_db)
) -> AsyncIterator[TurnEvent]:
    """The same patient turn, watched as it happens.

    Server-Sent Events because this is one-way and short-lived: the browser
    reads it with `fetch`, and nothing here needs a socket, a broker or a
    second connection. Failures become a final `error` frame rather than a
    status code — by then the response has already begun. That includes the
    404 from `_load`: FastAPI has already committed to a 200 by the time this
    generator is first advanced.
    """
    try:
        session, case = _load(db, session_id)
        async for event in process_turn(
            db, session, case, payload.content, channel=payload.channel
        ):
            yield event
    except HTTPException as exc:
        yield TurnEvent(type="error", status=exc.status_code, detail=str(exc.detail))
    except Exception:
        logger.exception("Intake stream failed for session %s", session_id)
        db.rollback()
        yield TurnEvent(
            type="error",
            status=500,
            detail="The assistant could not finish that answer. Please try again.",
        )
