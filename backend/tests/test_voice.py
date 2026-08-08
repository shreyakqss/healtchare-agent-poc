"""The audio plumbing around the voice models.

The models themselves are not exercised here: they are a few hundred megabytes
and several seconds per call, which does not belong in a suite that runs in a
fifth of a second. What *is* worth pinning is everything between the wire and
the model — decoding, mono downmix, resampling, and the guards that turn bad
audio into a 4xx instead of an OOM — because that is the code we wrote.

Run `python -m pytest tests/test_voice.py` after changing `services/voice.py`.
For an end-to-end check against the real models, synthesise a phrase and
transcribe it back (see the voice section of CLAUDE.md).
"""

import io
import math
import wave

import pytest

from services import voice

numpy = pytest.importorskip("numpy", reason="numpy ships with the voice extras")


def make_wav(seconds=0.25, rate=16_000, channels=1, width=2, freq=440.0) -> bytes:
    """A synthetic tone, in the shape the browser uploads."""
    frames = int(rate * seconds)
    samples = []
    for i in range(frames):
        value = int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / rate))
        samples.extend([value] * channels)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(numpy.array(samples, dtype=numpy.int16).tobytes())
    return buffer.getvalue()


def test_reads_16k_mono_unchanged():
    samples = voice._read_wav(make_wav(seconds=0.5))
    assert len(samples) == 8_000
    assert samples.dtype == numpy.float32
    assert -1.0 <= float(samples.min()) and float(samples.max()) <= 1.0


def test_resamples_to_the_rate_the_model_expects():
    """A 44.1 kHz upload must still reach Moonshine at 16 kHz."""
    samples = voice._read_wav(make_wav(seconds=1.0, rate=44_100))
    assert abs(len(samples) - voice.SAMPLE_RATE) <= 1


def test_downmixes_stereo():
    samples = voice._read_wav(make_wav(seconds=0.5, channels=2))
    assert len(samples) == 8_000  # frames, not interleaved samples


def test_rejects_empty_recording():
    with pytest.raises(ValueError, match="empty"):
        voice._read_wav(make_wav(seconds=0))


def test_rejects_audio_longer_than_a_turn():
    """The length guard runs off the header, so this allocates nothing."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(voice.SAMPLE_RATE)
        wav.writeframes(b"\x00\x00" * (voice.SAMPLE_RATE * (voice.MAX_AUDIO_SECONDS + 1)))
    with pytest.raises(ValueError, match="longer than"):
        voice._read_wav(buffer.getvalue())


def test_rejects_non_wav_upload():
    with pytest.raises(ValueError, match="not a readable WAV|Not a readable WAV"):
        voice._read_wav(b"this is not audio")


def test_rejects_non_16_bit_audio():
    with pytest.raises(ValueError, match="16-bit"):
        voice._read_wav(make_wav(width=1))


def test_wav_round_trip_preserves_samples():
    """What TTS emits must decode back to what it emitted."""
    original = numpy.linspace(-0.9, 0.9, 400, dtype=numpy.float32)
    decoded = voice._read_wav(voice._write_wav(voice.SAMPLE_RATE, original))
    assert len(decoded) == len(original)
    # 16-bit quantisation is the only loss.
    assert float(numpy.abs(decoded - original).max()) < 1e-3


def test_write_wav_accepts_int16_from_the_model():
    """Kokoro may hand back int16 or float32; both must encode."""
    ints = (numpy.linspace(-0.9, 0.9, 200) * 32767).astype(numpy.int16)
    decoded = voice._read_wav(voice._write_wav(voice.SAMPLE_RATE, ints))
    assert len(decoded) == 200


"""--- speech segmentation ---------------------------------------------------

Pure text, so unlike the models it is cheap to pin down properly. What matters
is that a streamed reply is cut into whole phrases: never mid-word, never one
piece per token, and never held back forever waiting for a full stop.
"""


def stream(text: str, size: int = 7) -> list[str]:
    """Feed `text` through the splitter in chunks, as a model would produce it."""
    segments, buffer = [], ""
    for start in range(0, len(text), size):
        ready, buffer = voice.split_for_speech(buffer + text[start : start + size])
        segments += ready
    tail, buffer = voice.split_for_speech(buffer, final=True)
    assert buffer == ""
    return segments + tail


def test_splits_on_sentences_and_loses_nothing():
    text = (
        "Thanks for sharing that information. Since you mentioned chest pain, "
        "I have one more question. How long has it been going on?"
    )
    segments = stream(text)
    assert len(segments) == 3
    assert segments[0] == "Thanks for sharing that information."
    assert "".join(segments).replace(" ", "") == text.replace(" ", "")


def test_first_segment_arrives_before_the_reply_is_finished():
    """The whole point: speech starts on sentence one, not on the last token."""
    ready, rest = voice.split_for_speech(
        "Thanks for telling me that. Now, how long ha"
    )
    assert ready == ["Thanks for telling me that."]
    assert rest.strip() == "Now, how long ha"


def test_short_replies_are_not_chopped_into_scraps():
    assert voice.split_for_speech("Yes. No. ")[0] == []
    assert stream("Yes. No.") == ["Yes. No."]


def test_a_decimal_is_not_a_sentence_end():
    ready, _ = voice.split_for_speech("You said it started 2.5 days ago and t")
    assert ready == []


def test_long_clauses_break_at_a_comma():
    text = (
        "I understand that you have been feeling unwell since the weekend and "
        "that it has been getting worse, which is useful for the clinician to "
        "know before you arrive"
    )
    segments = stream(text)
    assert len(segments) > 1
    assert segments[0].endswith(",")


def test_unpunctuated_rambling_is_still_spoken():
    text = "so " * 120
    segments = stream(text)
    assert segments
    assert all(len(piece) <= voice.MAX_SEGMENT_CHARS for piece in segments)
    # Broken on words, never mid-word.
    assert all(piece.strip() == piece for piece in segments)
    assert "".join(segments).replace(" ", "") == text.replace(" ", "")


def test_status_never_loads_a_model():
    """The UI probes this on every render; it must stay cheap."""
    report = voice.status()
    assert set(report) >= {"available", "stt_model", "tts_model"}
    assert report["stt_model"] == voice.STT_MODEL
