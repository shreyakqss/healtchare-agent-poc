"""Local speech-to-text and text-to-speech. The entire voice layer.

Both models come from `fastrtc` — Moonshine for STT, Kokoro for TTS, the same
components as the reference local-voice-ai-agent project, running on-device via
ONNX. Nothing here is sent to a cloud service.

**This module knows nothing about healthcare.** It converts audio to text and
text to audio; deciding what any of it means is the agents' job, and voice
input reaches them through `api.intake.process_turn` like any typed turn. Keep
it that way — a transcript is a patient statement, not a triage input.

What is *not* used from the reference project: its FastRTC `Stream` /
`ReplyOnPause` WebRTC transport, and its Ollama conversation loop. The loop is
the part we must not have — the healthcare workflow generates the replies. The
transport was skipped because intake is turn-based and every turn is bound to a
`IntakeSession` row; a WebRTC peer connection would need a second, parallel
notion of session state to carry that id. Plain multipart keeps the patient API
identical for the UI and for the future patient simulator. Revisit if
barge-in-quality latency ever matters more than that.

Audio arrives as 16 kHz mono WAV — the browser downsamples and encodes, so the
server needs no codec beyond the standard library's `wave`.
"""

from __future__ import annotations

import io
import logging
import wave

logger = logging.getLogger(__name__)

STT_MODEL = "moonshine/base"
TTS_MODEL = "kokoro"
TTS_VOICE = "af_heart"
SAMPLE_RATE = 16_000

# A patient turn is a sentence or two. Anything longer is a stuck recorder.
MAX_AUDIO_SECONDS = 120


class VoiceUnavailable(RuntimeError):
    """The local voice models are not installed or failed to load.

    Always recoverable from the patient's side: voice is an optional input
    channel and text intake is unaffected.
    """


# Loaded on first use, not at import: the models are a few hundred MB and the
# API must start (and text intake must work) without them.
_stt = None
_tts = None
_load_error: str | None = None


def _require_fastrtc():
    global _load_error
    try:
        import fastrtc  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        _load_error = (
            "The local voice models are not installed. Run "
            '`pip install "fastrtc[stt,tts]"` in the backend environment.'
        )
        raise VoiceUnavailable(_load_error) from exc


def stt_model():
    global _stt
    if _stt is None:
        _require_fastrtc()
        from fastrtc import get_stt_model

        logger.info("Loading local STT model %s (first call downloads it)", STT_MODEL)
        _stt = get_stt_model(STT_MODEL)
    return _stt


def tts_model():
    global _tts
    if _tts is None:
        _require_fastrtc()
        from fastrtc import get_tts_model

        logger.info("Loading local TTS model %s (first call downloads it)", TTS_MODEL)
        _tts = get_tts_model(TTS_MODEL)
    return _tts


def status() -> dict:
    """Whether voice is usable, without loading the models to find out.

    The UI probes this to decide whether to offer voice mode at all, so it must
    stay cheap — an import check, not a model load.
    """
    try:
        import fastrtc  # noqa: F401
    except ImportError:
        return {
            "available": False,
            "detail": (
                "Local voice models are not installed. Run "
                '`pip install "fastrtc[stt,tts]"` in the backend environment.'
            ),
            "stt_model": STT_MODEL,
            "tts_model": TTS_MODEL,
        }
    return {
        "available": True,
        "detail": None,
        "stt_model": STT_MODEL,
        "tts_model": TTS_MODEL,
        "loaded": {"stt": _stt is not None, "tts": _tts is not None},
    }


# --- cutting a growing reply into speakable pieces --------------------------
#
# A streamed reply has to be spoken before it is finished, and the unit of
# speech is a phrase, not a token: one synthesis request per token would be
# both unusable and absurd. The cut points are ordinary punctuation — a
# sentence first, a clause once a sentence has run long, and a hard ceiling so
# that a model rambling without punctuation is still heard.
#
# Pure text in, pure text out. No model is loaded, so `api/intake.py` can
# import this without dragging the ONNX stack into text-only intake.

SENTENCE_END = ".!?…"
CLAUSE_END = ",;:"
# Below this a segment is not worth its own request ("Yes." can wait for the
# rest of the sentence).
MIN_SEGMENT_CHARS = 20
# Long enough that breaking at a comma beats waiting for the full stop.
CLAUSE_SEGMENT_CHARS = 90
# Unpunctuated prose still has to be said eventually.
MAX_SEGMENT_CHARS = 180


def split_for_speech(buffer: str, *, final: bool = False) -> tuple[list[str], str]:
    """Cut `buffer` at natural speech boundaries.

    Returns the segments ready to synthesise and whatever is left over. Feed it
    the leftover plus each new chunk as the reply streams in, then call it once
    with ``final=True`` to flush the tail.

    A boundary only counts when whitespace follows it, so mid-stream the "2." of
    "2.5 days" is never mistaken for the end of a sentence. That costs one more
    chunk of latency and is why `final` exists.
    """
    segments: list[str] = []
    while (cut := _cut_point(buffer)) is not None:
        piece, buffer = buffer[:cut].strip(), buffer[cut:]
        if piece:
            segments.append(piece)

    if final:
        tail = buffer.strip()
        if tail:
            segments.append(tail)
        buffer = ""

    return segments, buffer


def _cut_point(buffer: str) -> int | None:
    """Index just past the first good break, or None to keep buffering."""
    if len(buffer) < MIN_SEGMENT_CHARS:
        return None

    for index in range(MIN_SEGMENT_CHARS - 1, len(buffer)):
        char = buffer[index]
        if not buffer[index + 1 : index + 2].isspace():
            continue
        if char in SENTENCE_END:
            return index + 1
        if char in CLAUSE_END and index + 1 >= CLAUSE_SEGMENT_CHARS:
            return index + 1

    if len(buffer) >= MAX_SEGMENT_CHARS:
        # No punctuation in sight — break on a word instead of mid-word.
        space = buffer.rfind(" ", MIN_SEGMENT_CHARS, MAX_SEGMENT_CHARS)
        return space + 1 if space > 0 else MAX_SEGMENT_CHARS

    return None


# --- wav <-> samples --------------------------------------------------------


def _read_wav(data: bytes):
    """Decode 16-bit PCM WAV to mono float32 at `SAMPLE_RATE`.

    Validates rather than trusts: this is a trust boundary, and a malformed or
    absurdly long upload should be a 4xx, not an OOM.
    """
    import numpy as np

    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.getnframes()
            if width != 2:
                raise ValueError(f"Expected 16-bit PCM audio, got {width * 8}-bit.")
            if frames == 0:
                raise ValueError("The recording is empty.")
            if frames / rate > MAX_AUDIO_SECONDS:
                raise ValueError(
                    f"Recording is longer than {MAX_AUDIO_SECONDS}s. Speak in "
                    "shorter turns."
                )
            raw = wav.readframes(frames)
    except wave.Error as exc:
        raise ValueError(f"Not a readable WAV recording: {exc}") from exc

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if rate != SAMPLE_RATE:
        # Linear resample. The browser already sends 16 kHz; this is the guard
        # for anything that does not (a simulator posting a fixture, say).
        target_len = int(round(len(samples) * SAMPLE_RATE / rate))
        samples = np.interp(
            np.linspace(0, len(samples), target_len, endpoint=False),
            np.arange(len(samples)),
            samples,
        ).astype(np.float32)

    return samples


def _write_wav(sample_rate: int, samples) -> bytes:
    """Encode float32 [-1, 1] or int16 samples to a 16-bit PCM WAV."""
    import numpy as np

    array = np.asarray(samples).squeeze()
    if array.dtype != np.int16:
        array = np.clip(array, -1.0, 1.0)
        array = (array * 32767).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(array.tobytes())
    return buffer.getvalue()


# --- the two operations -----------------------------------------------------


def transcribe(wav_bytes: bytes) -> str:
    """Spoken audio -> text. Raises ValueError on unusable audio."""
    samples = _read_wav(wav_bytes)
    # Moonshine takes (sample_rate, (channels, samples)).
    audio = (SAMPLE_RATE, samples.reshape(1, -1))
    try:
        text = stt_model().stt(audio)
    except VoiceUnavailable:
        raise
    except Exception as exc:  # the ONNX stack raises its own error types
        logger.exception("Local STT failed")
        raise VoiceUnavailable(f"Speech recognition failed: {exc}") from exc
    return (text or "").strip()


def synthesise(text: str) -> bytes:
    """Assistant text -> spoken WAV."""
    try:
        model = tts_model()
        from fastrtc import KokoroTTSOptions

        sample_rate, samples = model.tts(
            text, options=KokoroTTSOptions(voice=TTS_VOICE, speed=1.0, lang="en-us")
        )
    except VoiceUnavailable:
        raise
    except Exception as exc:  # pragma: no cover - model/runtime failure
        logger.exception("Local TTS failed")
        raise VoiceUnavailable(f"Speech synthesis failed: {exc}") from exc
    return _write_wav(sample_rate, samples)
