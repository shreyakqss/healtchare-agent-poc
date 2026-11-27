"""AI reads of uploaded files that have no extractable text: images (X-rays, photos, scans) and
scanned PDFs. Drafted at pre-screening, after urgency and routing are decided, and stored as a
ClinicalSummary of kind `file_reads`. Clinician-facing only: it may feed the AI differential and the
doctor assistant as context (like report text), but it never becomes a PatientFact, never reaches
triage or routing, and is not on the patient projection. A read that fails or is slow is marked
"unavailable" and pre-screening carries on - it never blocks the case.

There is no chunking or retrieval: each file goes to the model whole. So the limits in settings
(FILE_READ_*) are checked here before anything is sent - a file outside them is marked "skipped"
with the reason, costs nothing, and stays for the doctor to open.
"""

from __future__ import annotations

import asyncio
import io
import logging
import uuid

from pypdf import PdfReader, PdfWriter
from sqlalchemy.orm import Session

from app.agents import AgentUnavailable, file_reader
from app.core.config import settings
from app.models import ClinicalSummary, MedicalAttachment
from app.services import attachments, audit, case_repo

logger = logging.getLogger(__name__)

KIND = "file_reads"
LABEL = "AI read, not a radiology report"
READ_TIMEOUT_SECONDS = 30
READABLE_IMAGES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class Skip(Exception):
    """The file is outside the read limits; the message is shown to the doctor."""


def unread(db: Session, case_id: uuid.UUID) -> list[MedicalAttachment]:
    """The case's files the text extractor could not read but the model can look at."""
    return [
        a for a in case_repo.attachments(db, case_id)
        if not a.extracted_text and (a.mime_type in READABLE_IMAGES or a.mime_type == "application/pdf")
    ]


def _first_pages(content: bytes) -> tuple[bytes, int, int]:
    """The PDF cut to its first FILE_READ_MAX_PDF_PAGES pages: (bytes, pages sent, pages in file)."""
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise Skip("Password-protected PDF, not sent to the AI.")
        total = len(reader.pages)
    except Skip:
        raise
    except Exception as exc:
        raise Skip("The PDF could not be opened.") from exc
    limit = settings.FILE_READ_MAX_PDF_PAGES
    if total <= limit:
        return content, total, total
    writer = PdfWriter()
    for page in reader.pages[:limit]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), limit, total


def _prepare(a: MedicalAttachment) -> tuple[bytes, dict]:
    """What is sent for this file, and what the doctor is told about it. Raises Skip."""
    content = attachments.absolute_path(a.storage_uri).read_bytes()
    if a.mime_type == "application/pdf":
        content, sent, total = _first_pages(content)
        return content, {"pages_read": sent, "pages_total": total}
    if len(content) > settings.FILE_READ_MAX_IMAGE_MB * 1024 * 1024:
        raise Skip(f"Image is over {settings.FILE_READ_MAX_IMAGE_MB:g} MB, too large for the AI to read.")
    return content, {}


async def _read_one(a: MedicalAttachment, reason: str) -> dict:
    base = {"attachment_id": str(a.id), "filename": a.filename, "kind": a.kind}
    try:
        content, extra = _prepare(a)
    except Skip as skip:
        return {**base, "status": "skipped", "note": str(skip)}
    except OSError:
        return {**base, "status": "skipped", "note": "The stored file could not be found."}
    note = ""
    if extra.get("pages_total", 0) > extra.get("pages_read", 0):
        note = f"Only the first {extra['pages_read']} of {extra['pages_total']} pages are attached."
    try:
        result = await asyncio.wait_for(
            file_reader.read(content, a.mime_type, a.kind, reason, note), READ_TIMEOUT_SECONDS,
        )
    except (AgentUnavailable, TimeoutError) as exc:
        logger.warning("File reader unavailable (%s)", type(exc).__name__)
        return {**base, **extra, "status": "unavailable"}
    return {**base, **extra, "status": "read", **result.model_dump()}


async def read_case(db: Session, case_id: uuid.UUID, actor: str) -> ClinicalSummary | None:
    """Read the case's unread files, at most FILE_READ_MAX_FILES; None when there is nothing to read."""
    files = unread(db, case_id)
    if not files:
        return None
    limit = settings.FILE_READ_MAX_FILES
    reason = "; ".join(f.value for f in case_repo.facts(db, case_id) if f.kind == "reason_for_visit")
    reads = list(await asyncio.gather(*(_read_one(a, reason) for a in files[:limit])))
    reads += [
        {"attachment_id": str(a.id), "filename": a.filename, "kind": a.kind, "status": "skipped",
         "note": f"Not read: the AI reads at most {limit} files per visit."}
        for a in files[limit:]
    ]
    done = sum(1 for r in reads if r["status"] == "read")
    summary = ClinicalSummary(
        case_id=case_id, kind=KIND, sections={"label": LABEL, "reads": reads},
        generated_by="llm" if done else "none",
    )
    db.add(summary)
    # Counts only: the read itself is clinical content and lives on the summary.
    audit.record(db, case_id, actor, "file_read.completed", {
        "files": len(reads), "read": done,
        "skipped": sum(1 for r in reads if r["status"] == "skipped"),
        "unavailable": sum(1 for r in reads if r["status"] == "unavailable"),
    })
    return summary


def context_lines(db: Session, case_id: uuid.UUID) -> list[str]:
    """The reads as plain lines for the clinician agents, each labelled as an AI read."""
    summary = case_repo.summary(db, case_id, KIND)
    lines: list[str] = []
    for r in (summary.sections.get("reads") if summary else None) or []:
        if r.get("status") != "read":
            continue
        body = "; ".join([r.get("what_it_is") or "", *(r.get("findings") or []), r.get("impression") or ""])
        partial = (f" (first {r['pages_read']} of {r['pages_total']} pages)"
                   if r.get("pages_total", 0) > r.get("pages_read", 0) else "")
        lines.append(f"[{r['kind']}: {r['filename']}{partial} - {LABEL}] {body.strip('; ')}")
    return lines
