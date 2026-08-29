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
KIND_LABELS: dict[str, str] = {
    "lab_report": "Lab Report",
    "radiology": "Radiology Report",
    "prescription": "Prescription",
    "referral": "Referral",
    "discharge_summary": "Discharge Summary",
    "other": "Attachment",
}


def kind_label(kind: str) -> str:
    """Human title for an attachment kind (used as the HMS document title)."""
    return KIND_LABELS.get(kind, "Attachment")


# Coarse, advisory-only sanity check on extracted text vs. the declared attachment kind -
# NOT real document classification. A short list of words/phrases that would plausibly
# appear in a genuine document of that kind; if a document has extracted text but matches
# none of its kind's keywords, that's a signal worth a clinician's attention, never a
# reason to block the upload (this codebase's established "required-with-skip, never
# hard-block" philosophy for uploads - see AttachmentSkipRequest). "other" has no keyword
# set (nothing plausible to check against) and is skipped entirely.
KIND_KEYWORDS: dict[str, list[str]] = {
    "lab_report": [
        "result", "reference range", "specimen", "normal", "abnormal", "panel",
        "mg/dl", "mmol/l", "g/dl", "units/l", "positive", "negative", "test",
    ],
    "prescription": [
        "mg", "mcg", "tablet", "capsule", "dose", "dosage", "twice daily", "once daily",
        "rx", "refill", "prescri",  # matches "prescribe"/"prescription"/"prescribed"
    ],
    "radiology": [
        "x-ray", "xray", "ct scan", "mri", "ultrasound", "impression", "findings",
        "radiolog", "contrast", "imaging",
    ],
    "discharge_summary": [
        "discharge", "admission", "admitted", "hospital course", "diagnosis",
        "follow-up", "discharged on",
    ],
    "referral": [
        "referral", "referring", "refer to", "please see", "consult", "specialist",
    ],
}


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
        # path.name is a random uuid, not PHI; exc could echo extracted document
        # text in some parser error messages, so only its type is logged.
        logger.warning("Text extraction failed (%s)", type(exc).__name__)
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
    root = settings.UPLOAD_DIR.resolve()
    path = (root / storage_uri).resolve()
    if path != root and root not in path.parents:
        raise FileNotFoundError("Stored file path is outside the upload directory.")
    return path


def kind_mismatch_suspected(kind: str, extracted_text: str | None) -> bool:
    """True when extracted text exists but contains none of the declared kind's plausible
    keywords - advisory only (see KIND_KEYWORDS comment). Never used to block an upload;
    the caller (api/v1/cases.py) decides what to do with a True result (write an advisory
    record for the clinician)."""
    keywords = KIND_KEYWORDS.get(kind)
    if not keywords or not extracted_text:
        return False
    haystack = extracted_text.lower()
    return not any(kw in haystack for kw in keywords)
