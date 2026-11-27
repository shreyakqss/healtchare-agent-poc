"""AI reads of uploaded images / scanned PDFs: limits are checked before anything is sent, a failure
or slow read never raises, and the reads reach the clinician agents only as labelled AI reads."""

import asyncio
import io
import uuid
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter

from app.agents import AgentUnavailable
from app.agents.schemas import FileRead
from app.services import file_read_service as svc

READ = FileRead(what_it_is="Chest X-ray", findings=["Right lower zone opacity"], impression="Possible consolidation", limitations="")


def _pdf(pages: int, password: str | None = None) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    if password:
        w.encrypt(password)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


@pytest.fixture
def stored(tmp_path, monkeypatch):
    """Write `content` as an attachment file and return the attachment row."""
    monkeypatch.setattr(svc.attachments, "absolute_path", lambda uri: tmp_path / uri)

    def make(content: bytes, mime="image/png", name="xray.png"):
        (tmp_path / name).write_bytes(content)
        return SimpleNamespace(id=uuid.uuid4(), filename=name, kind="radiology", mime_type=mime,
                               storage_uri=name, extracted_text=None)
    return make


@pytest.fixture
def sent(monkeypatch):
    """Replace the model with a recorder; returns what each call was sent."""
    calls: list[dict] = []

    async def fake(content, mime, kind, reason, note=""):
        calls.append({"content": content, "mime": mime, "note": note})
        return READ
    monkeypatch.setattr(svc.file_reader, "read", fake)
    return calls


def test_model_failure_marks_unavailable(stored, monkeypatch):
    async def down(*_a, **_k):
        raise AgentUnavailable("down")
    monkeypatch.setattr(svc.file_reader, "read", down)
    assert asyncio.run(svc._read_one(stored(b"png"), "cough"))["status"] == "unavailable"


def test_slow_read_times_out(stored, monkeypatch):
    async def slow(*_a, **_k):
        await asyncio.sleep(5)
    monkeypatch.setattr(svc.file_reader, "read", slow)
    monkeypatch.setattr(svc, "READ_TIMEOUT_SECONDS", 0.05)
    assert asyncio.run(svc._read_one(stored(b"png"), ""))["status"] == "unavailable"


def test_image_is_read(stored, sent):
    out = asyncio.run(svc._read_one(stored(b"png"), "cough"))
    assert out["status"] == "read" and out["findings"] == ["Right lower zone opacity"]


def test_oversized_image_is_never_sent(stored, sent, monkeypatch):
    monkeypatch.setattr(svc.settings, "FILE_READ_MAX_IMAGE_MB", 0.001)
    out = asyncio.run(svc._read_one(stored(b"x" * 5000), "cough"))
    assert out["status"] == "skipped" and "too large" in out["note"] and sent == []


def test_long_pdf_sends_only_the_first_pages(stored, sent, monkeypatch):
    monkeypatch.setattr(svc.settings, "FILE_READ_MAX_PDF_PAGES", 3)
    out = asyncio.run(svc._read_one(stored(_pdf(8), "application/pdf", "scan.pdf"), "cough"))
    assert out["status"] == "read" and (out["pages_read"], out["pages_total"]) == (3, 8)
    assert len(PdfReader(io.BytesIO(sent[0]["content"])).pages) == 3
    assert "first 3 of 8" in sent[0]["note"]


def test_short_pdf_is_sent_whole(stored, sent):
    content = _pdf(2)
    asyncio.run(svc._read_one(stored(content, "application/pdf", "scan.pdf"), ""))
    assert sent[0]["content"] == content and sent[0]["note"] == ""


def test_encrypted_pdf_is_skipped(stored, sent):
    out = asyncio.run(svc._read_one(stored(_pdf(1, "secret"), "application/pdf", "scan.pdf"), ""))
    assert out["status"] == "skipped" and "Password" in out["note"] and sent == []


def test_unread_skips_files_with_text(monkeypatch):
    def att(mime, text=None):
        return SimpleNamespace(id=uuid.uuid4(), mime_type=mime, extracted_text=text)
    texted, scanned, image = att("application/pdf", "Hb 12"), att("application/pdf"), att("image/png")
    monkeypatch.setattr(svc.case_repo, "attachments", lambda db, cid: [texted, scanned, image])
    assert svc.unread(None, uuid.uuid4()) == [scanned, image]


def test_context_lines_are_labelled_and_skip_failures(monkeypatch):
    reads = [
        {"attachment_id": "1", "filename": "xray.png", "kind": "radiology", "status": "read",
         "what_it_is": "Chest X-ray", "findings": ["Right lower zone opacity"], "impression": "Possible consolidation"},
        {"attachment_id": "2", "filename": "scan.pdf", "kind": "lab_report", "status": "read",
         "pages_read": 10, "pages_total": 14, "what_it_is": "CBC", "findings": [], "impression": ""},
        {"attachment_id": "3", "filename": "big.png", "kind": "other", "status": "skipped", "note": "too large"},
    ]
    monkeypatch.setattr(svc.case_repo, "summary", lambda db, cid, kind: SimpleNamespace(sections={"reads": reads}))
    lines = svc.context_lines(None, uuid.uuid4())
    assert len(lines) == 2
    assert svc.LABEL in lines[0] and "Right lower zone opacity" in lines[0]
    assert "first 10 of 14 pages" in lines[1]


# --- typed documents and prescriptions --------------------------------------------------------

def test_typed_document_is_summarised_from_its_text(monkeypatch):
    seen: dict = {}

    async def fake_text(text, kind, reason):
        seen["text"] = text
        return FileRead(what_it_is="Prescription", findings=["Metformin 500 mg BD"], impression="", limitations="")
    monkeypatch.setattr(svc.file_reader, "read_text", fake_text)
    doc = SimpleNamespace(id=uuid.uuid4(), filename="rx.pdf", kind="prescription", mime_type="application/pdf",
                          storage_uri="rx.pdf", extracted_text="Metformin 500 mg BD " * 1000)
    out = asyncio.run(svc._summarise_one(doc, "diabetes review"))
    assert out["status"] == "read" and out["source"] == "text" and out["label"] == svc.TEXT_LABEL
    assert len(seen["text"]) == svc.MAX_TEXT_CHARS  # capped before it is sent


def test_summary_lines_cover_every_upload_but_agents_get_typed_text_once(monkeypatch):
    reads = [
        {"attachment_id": "1", "filename": "xray.png", "kind": "radiology", "status": "read", "source": "file",
         "label": svc.LABEL, "what_it_is": "Chest X-ray", "findings": ["RLZ opacity"], "impression": "Possible pneumonia"},
        {"attachment_id": "2", "filename": "rx.pdf", "kind": "prescription", "status": "read", "source": "text",
         "label": svc.TEXT_LABEL, "what_it_is": "Prescription", "findings": ["Metformin 500 mg BD"], "impression": ""},
        {"attachment_id": "3", "filename": "big.png", "kind": "other", "status": "skipped", "note": "too large"},
    ]
    monkeypatch.setattr(svc.case_repo, "summary", lambda db, cid, kind: SimpleNamespace(sections={"reads": reads}))
    lines = svc.summary_lines(None, uuid.uuid4())
    assert len(lines) == 3 and "Metformin 500 mg BD" in lines[1] and "not read" in lines[2]
    context = svc.context_lines(None, uuid.uuid4())
    # The typed prescription's raw text already reaches the agents; only the image read is added.
    assert len(context) == 1 and "xray.png" in context[0]


def test_photographed_prescription_medicines_are_read_from_the_image(monkeypatch):
    from app.agents.schemas import MedicationCandidatesResult
    from app.services import attachment_service

    calls: list[str] = []

    async def from_file(content, mime):
        calls.append(mime)
        return MedicationCandidatesResult(medications=["Metformin", "Atorvastatin"])
    monkeypatch.setattr(attachment_service, "extract_medications_from_file", from_file)
    meds, source = asyncio.run(attachment_service._prescription_medicines(None, b"png-bytes", "image/png"))
    assert meds == ["Metformin", "Atorvastatin"] and source == "image" and calls == ["image/png"]

    # Outside the limits: nothing is sent and the upload carries on with no candidates.
    big = b"x" * int(svc.settings.FILE_READ_MAX_IMAGE_MB * 1024 * 1024 + 1)
    calls.clear()
    assert asyncio.run(attachment_service._prescription_medicines(None, big, "image/png")) == ([], "none")
    assert calls == []

    async def down(*_a, **_k):
        raise AgentUnavailable("down")
    monkeypatch.setattr(attachment_service, "extract_medications_from_file", down)
    assert asyncio.run(attachment_service._prescription_medicines(None, b"png", "image/png")) == ([], "none")
