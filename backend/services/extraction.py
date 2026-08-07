"""Storage and text extraction for uploaded medical records.

Scope boundary, straight from the foundation doc: documents get their text
extracted so a clinician can read them alongside the case; **images are stored
and displayed only**. Nothing here interprets an image, and nothing here
returns anything the triage engine consumes.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# Extension allowlist. Trust boundary: the client-supplied content type is a
# hint, not evidence, so the extension decides and anything unlisted is refused.
DOCUMENT_EXTENSIONS = {".pdf", ".txt", ".md", ".rtf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".dcm"}
ALLOWED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

ATTACHMENT_KINDS = {
    "radiology",
    "pathology",
    "lab_report",
    "prescription",
    "referral",
    "other",
}


class UploadRejected(ValueError):
    """The upload failed validation and was never written to disk."""


@dataclass
class StoredAttachment:
    filename: str
    mime_type: str
    size_bytes: int
    storage_uri: str
    extracted_text: str | None
    is_image: bool


def validate(filename: str, size_bytes: int, kind: str) -> str:
    """Check an upload before any bytes touch the filesystem. Returns the extension."""
    if kind not in ATTACHMENT_KINDS:
        raise UploadRejected(
            f"Unknown attachment kind '{kind}'. Expected one of: "
            f"{', '.join(sorted(ATTACHMENT_KINDS))}."
        )

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadRejected(
            f"File type '{extension or 'unknown'}' is not accepted. Allowed: "
            f"{', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise UploadRejected(
            f"File is {size_bytes / 1024 / 1024:.1f} MB, over the "
            f"{settings.MAX_UPLOAD_MB} MB limit."
        )
    if size_bytes == 0:
        raise UploadRejected("File is empty.")

    return extension


def _extract_pdf_text(path: Path) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        return text or None
    except Exception as exc:  # a corrupt upload must not take down the request
        logger.warning("PDF text extraction failed for %s: %s", path.name, exc)
        return None


def _extract_plain_text(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return text or None
    except OSError as exc:
        logger.warning("Text read failed for %s: %s", path.name, exc)
        return None


def store(
    case_id: uuid.UUID, filename: str, content: bytes, kind: str
) -> StoredAttachment:
    """Validate, write to the upload directory, and extract text if it's a document."""
    extension = validate(filename, len(content), kind)

    case_dir = Path(settings.UPLOAD_DIR) / str(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)

    # Never reuse the client's filename on disk — it is attacker-controlled and
    # would allow path traversal or collisions between cases.
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = case_dir / stored_name
    destination.write_bytes(content)

    is_image = extension in IMAGE_EXTENSIONS

    if is_image:
        extracted_text = None  # images are stored and displayed only
    elif extension == ".pdf":
        extracted_text = _extract_pdf_text(destination)
    else:
        extracted_text = _extract_plain_text(destination)

    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    return StoredAttachment(
        filename=Path(filename).name,
        mime_type=mime_type,
        size_bytes=len(content),
        storage_uri=str(destination.relative_to(settings.UPLOAD_DIR)).replace("\\", "/"),
        extracted_text=extracted_text,
        is_image=is_image,
    )


def absolute_path(storage_uri: str) -> Path:
    """Resolve a stored URI back to a path, refusing anything outside UPLOAD_DIR."""
    root = Path(settings.UPLOAD_DIR).resolve()
    candidate = (root / storage_uri).resolve()
    if not candidate.is_relative_to(root):
        raise UploadRejected("Refusing to read a path outside the upload directory.")
    return candidate
