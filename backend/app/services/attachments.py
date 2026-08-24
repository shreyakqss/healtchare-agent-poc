"""Storage and text extraction for uploaded records.

Documents get text extracted for the clinician to read; images are stored and
displayed only. Nothing here is consumed by the triage engine.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import DomainError

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
ATTACHMENT_KINDS = {"lab_report", "radiology", "prescription", "referral", "discharge_summary", "other"}


class UploadRejected(DomainError):
    status_code = 400


@dataclass
class Stored:
    filename: str
    mime_type: str
    size_bytes: int
    storage_uri: str
    extracted_text: str | None


def _validate(filename: str, size: int, kind: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadRejected(f"File type {ext or '(none)'} is not accepted. Upload a PDF, text file or image.")
    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise UploadRejected(f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    if kind not in ATTACHMENT_KINDS:
        raise UploadRejected(f"Unknown attachment kind {kind!r}.")
    return ext


def _extract_text(path: Path, ext: str) -> str | None:
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages).strip() or None
        if ext in DOCUMENT_EXTENSIONS:
            return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except Exception as exc:  # extraction is best effort; the file is still stored
        logger.warning("Text extraction failed for %s: %s", path.name, exc)
    return None


def store(case_id: uuid.UUID, filename: str, content: bytes, kind: str) -> Stored:
    ext = _validate(filename, len(content), kind)
    folder = settings.UPLOAD_DIR / str(case_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(content)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Stored(
        filename=Path(filename).name,
        mime_type=mime,
        size_bytes=len(content),
        storage_uri=str(path.relative_to(settings.UPLOAD_DIR)).replace("\\", "/"),
        extracted_text=_extract_text(path, ext),
    )


def absolute_path(storage_uri: str) -> Path:
    return settings.UPLOAD_DIR / storage_uri