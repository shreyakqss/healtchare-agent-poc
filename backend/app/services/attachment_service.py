"""Attachment use cases: upload (store, advisory kind check, forward to the HMS) and skip.

Storage and text extraction live in `services/attachments.py`; this module owns the
case-level behaviour around them. Nothing here reaches `triage_engine.evaluate()`.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, Unprocessable
from app.domain.lifecycle import TERMINAL
from app.integrations.hms import get_hms
from app.models import ClinicalDiscrepancy, MedicalAttachment, PatientCase
from app.services import attachments as storage
from app.services import audit, case_repo
from app.services.hms import push_document_with_retry

ACTOR_ATTACHMENTS = "system:attachments"
ACTOR_HMS_SYNC = "system:hms_sync"


def _assert_patient_upload_allowed(db: Session, case: PatientCase) -> None:
    session = case_repo.session_for(db, case)
    if session.consent_status != "GRANTED":
        raise Forbidden("Consent must be granted before documents can be added.")
    if session.status in TERMINAL:
        raise Conflict(f"Documents cannot be changed after a case is {session.status.lower()}.")


async def upload(db: Session, case: PatientCase, filename: str, content: bytes, kind: str, uploaded_by: str) -> MedicalAttachment:
    """Store the file, record it, flag a kind mismatch for the clinician (advisory only)
    and best-effort forward it to the linked HMS record. Never blocks the upload."""
    _assert_patient_upload_allowed(db, case)
    stored = storage.store(case.id, filename, content, kind)
    row = MedicalAttachment(
        case_id=case.id, kind=kind, filename=stored.filename, mime_type=stored.mime_type,
        size_bytes=stored.size_bytes, storage_uri=stored.storage_uri, extracted_text=stored.extracted_text,
        uploaded_by=uploaded_by,
    )
    db.add(row)
    audit.record(db, case.id, uploaded_by, "attachment.uploaded", {
        "kind": kind, "filename": stored.filename, "size_bytes": stored.size_bytes,
        "text_extracted": bool(stored.extracted_text), "interpreted": False,
    })
    db.flush()  # row.id is referenced by the records below

    if storage.kind_mismatch_suspected(kind, stored.extracted_text):
        # Reuses ClinicalDiscrepancy (source_kind="document") rather than a new table.
        db.add(ClinicalDiscrepancy(
            case_id=case.id, field_or_topic="attachment_kind_mismatch",
            patient_stated=f"Uploaded as: {kind}",
            document_says="Extracted text did not match expected keywords for this kind.",
            source_kind="document", attachment_id=row.id, severity="info",
            requested_document_kind=None, generated_by="heuristic",
        ))
        audit.record(db, case.id, ACTOR_ATTACHMENTS, "attachment.kind_mismatch_suspected",
                     {"attachment_id": str(row.id), "kind": kind})

    if case.hms_patient_id:
        # Blocking HTTP plus a blocking sleep on retry - keep it off the event loop.
        reference, error_type = await asyncio.to_thread(
            push_document_with_retry, get_hms(), case.hms_patient_id,
            storage.kind_label(kind), content, stored.mime_type,
        )
        if reference is not None:
            row.hms_reference = reference
            audit.record(db, case.id, ACTOR_HMS_SYNC, "attachment.pushed_to_hms",
                         {"attachment_id": str(row.id), "hms_reference": reference})
        else:
            audit.record(db, case.id, ACTOR_HMS_SYNC, "attachment.push_to_hms_failed",
                         {"attachment_id": str(row.id), "error_type": error_type})

    db.commit()
    db.refresh(row)
    return row


def skip(db: Session, case: PatientCase, kind: str, reason: str | None) -> None:
    """A logged skip satisfies a required attachment kind the same way a file does."""
    _assert_patient_upload_allowed(db, case)
    if kind not in storage.ATTACHMENT_KINDS:
        raise Unprocessable(f"Unknown attachment kind {kind!r}.")
    audit.record(db, case.id, "patient", "attachment.skipped", {"kind": kind, "reason": reason})
    db.commit()
