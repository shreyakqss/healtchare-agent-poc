"""Voice as an *interface* to intake, not a second intake.

    speech --/voice/transcribe--> transcript --> POST /intake-sessions/{id}/messages
    agent reply --/voice/speech--> audio

Note what this module does **not** import: no agent, no graph, no triage, not
even the intake router. It converts audio to text and text to audio. The
transcript is then posted to the ordinary `/messages` endpoint — the same one a
typed turn uses and the same one the future patient simulator will use — so a
spoken turn is not merely *treated* like a typed turn, it literally is one by
the time the workflow sees it. There is no path by which this file can decide
a priority, route a patient, or generate a reply.

Audio is never persisted: it is read from the request, transcribed, and
dropped. The `IntakeMessage` row holding the transcript is the record.

Both models are local — Moonshine and Kokoro via `fastrtc`, the reference
project's components. See `services/voice.py`.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import AuditEvent, get_db
from services import voice

router = APIRouter(prefix="/voice", tags=["voice"])

# Speech at 16 kHz mono 16-bit is ~32 KB/s; this sits well above
# `voice.MAX_AUDIO_SECONDS` so the duration check gives the better message.
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    # Optional: lets synthesis be audited against the case it belongs to.
    case_id: uuid.UUID | None = None
    # Which piece of a streamed reply this is. A reply is spoken in phrases so
    # playback can start before the model has finished writing it; recording
    # the index is what makes "time to first audio" answerable afterwards.
    segment: int | None = None


class TranscriptResponse(BaseModel):
    transcript: str
    stt_ms: float
    model: str


def _audit(db: Session, case_id, action: str, payload: dict) -> None:
    """Voice events land in the same audit trail as the agents.

    `case_id` is optional on these endpoints — a caller with no case (a probe,
    a test) simply leaves no trace rather than being refused.
    """
    if case_id is None:
        return
    db.add(
        AuditEvent(case_id=case_id, actor="system:voice", action=action, payload=payload)
    )
    db.commit()


@router.get("/status")
def voice_status():
    """Cheap capability probe — the UI hides voice mode when unavailable.

    Deliberately does not load the models: this is called on every page render
    and a model load is hundreds of megabytes.
    """
    return voice.status()


@router.post("/transcribe", response_model=TranscriptResponse)
async def transcribe(
    audio: UploadFile = File(..., description="16 kHz mono 16-bit PCM WAV"),
    case_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Speech -> text. The caller decides what to do with the transcript."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="No audio was uploaded.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large.")

    _audit(
        db,
        case_id,
        "voice.input_received",
        {"bytes": len(data), "content_type": audio.content_type, "status": "ok"},
    )

    started = time.perf_counter()
    try:
        text = voice.transcribe(data)
    except ValueError as exc:
        # Unusable audio — the caller's to fix, not a server fault.
        _audit(
            db,
            case_id,
            "voice.stt_failed",
            {"reason": str(exc), "kind": "bad_audio", "status": "error"},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except voice.VoiceUnavailable as exc:
        _audit(
            db,
            case_id,
            "voice.stt_failed",
            {"reason": str(exc), "kind": "unavailable", "status": "error"},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    stt_ms = (time.perf_counter() - started) * 1000

    if not text:
        # Silence or noise. Nothing is submitted, so no empty turn is recorded.
        _audit(
            db,
            case_id,
            "voice.stt_failed",
            {
                "reason": "No speech detected.",
                "kind": "empty_transcript",
                "duration_ms": round(stt_ms, 1),
                "status": "error",
            },
        )
        raise HTTPException(
            status_code=422,
            detail="No speech was detected. Try again, or type your answer instead.",
        )

    _audit(
        db,
        case_id,
        "voice.transcribed",
        {
            "duration_ms": round(stt_ms, 1),
            "characters": len(text),
            "model": voice.STT_MODEL,
            "status": "ok",
        },
    )
    return TranscriptResponse(
        transcript=text, stt_ms=round(stt_ms, 1), model=voice.STT_MODEL
    )


@router.post("/speech")
def synthesise_speech(payload: SpeechRequest, db: Session = Depends(get_db)):
    """Text -> spoken WAV.

    Takes text rather than a message id on purpose: it speaks back whatever the
    workflow already produced and has no way to originate a reply of its own.
    """
    started = time.perf_counter()
    try:
        wav = voice.synthesise(payload.text)
    except voice.VoiceUnavailable as exc:
        _audit(
            db,
            payload.case_id,
            "voice.tts_failed",
            {"reason": str(exc), "segment": payload.segment, "status": "error"},
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    _audit(
        db,
        payload.case_id,
        "voice.synthesised",
        {
            "duration_ms": round(elapsed_ms, 1),
            "segment": payload.segment,
            "characters": len(payload.text),
            "model": voice.TTS_MODEL,
            "voice": voice.TTS_VOICE,
            "status": "ok",
        },
    )

    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"X-Synthesis-Ms": f"{elapsed_ms:.1f}", "Cache-Control": "no-store"},
    )
