"""Cases: read, attachments, pre-screening, consultation notes, finalisation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1 import serializers
from app.core.errors import Conflict, Forbidden, NotFound
from app.models import ConsultationNote, MedicalAttachment
from app.schemas.requests import ConsultationNoteRequest
from app.schemas.responses import (
    AttachmentResponse,
    CaseDetailResponse,
    CaseListItem,
    ClinicOverview,
    ConsultationNoteResponse,
)
from app.services import attachments as attachment_store
from app.services import audit, case_repo
from app.workflows import run_finalize, run_prescreen

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseListItem])
def list_cases(db: Session = Depends(get_db)):
    return serializers.case_list(db)


@router.get("/overview", response_model=ClinicOverview)
def clinic_overview(db: Session = Depends(get_db)):
    return serializers.overview(serializers.case_list(db))


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: uuid.UUID, db: Session = Depends(get_db)):
    return serializers.case_detail(db, case_repo.case_or_404(db, case_id))


@router.post("/{case_id}/attachments", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    uploaded_by: str = Form("patient"),
    db: Session = Depends(get_db),
):
    """Stored and displayed only. Nothing uploaded here can influence a priority."""
    case = case_repo.case_or_404(db, case_id)
    stored = attachment_store.store(case.id, file.filename or "upload", await file.read(), kind)
    row = MedicalAttachment(
        case_id=case.id, kind=kind, filename=stored.filename, mime_type=stored.mime_type, size_bytes=stored.size_bytes,
        storage_uri=stored.storage_uri, extracted_text=stored.extracted_text, uploaded_by=uploaded_by,
    )
    db.add(row)
    audit.record(db, case.id, uploaded_by, "attachment.uploaded",
                 {"kind": kind, "filename": stored.filename, "size_bytes": stored.size_bytes, "text_extracted": bool(stored.extracted_text), "interpreted": False})
    db.commit()
    db.refresh(row)
    return serializers.attachment_out(row)


@router.get("/{case_id}/attachments/{attachment_id}/file")
def download_attachment(case_id: uuid.UUID, attachment_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(MedicalAttachment, attachment_id)
    if row is None or row.case_id != case_id:
        raise NotFound("Attachment not found.")
    path = attachment_store.absolute_path(row.storage_uri)
    if not path.exists():
        raise NotFound("Stored file is missing.")
    return FileResponse(path, media_type=row.mime_type, filename=row.filename)


@router.post("/{case_id}/prescreen", response_model=CaseDetailResponse)
async def prescreen(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Rules -> routing -> briefing. Ends at NEEDS_REVIEW."""
    case = case_repo.case_or_404(db, case_id)
    session = case_repo.session_for(db, case)
    if session.consent_status != "GRANTED":
        raise Forbidden("Consent must be granted before pre-screening.")
    if session.status not in {"INGESTING", "ANALYZING", "FAILED"}:
        raise Conflict(f"Pre-screening cannot run while the case is {session.status}.")
    db.close()  # workflow steps open their own sessions
    await run_prescreen(case_id)
    return serializers.case_detail(db, case_repo.case_or_404(db, case_id))


@router.post("/{case_id}/consultation-notes", response_model=ConsultationNoteResponse, status_code=201)
def add_consultation_note(case_id: uuid.UUID, payload: ConsultationNoteRequest, db: Session = Depends(get_db)):
    case = case_repo.case_or_404(db, case_id)
    if not case_repo.is_approved(db, case.id):
        raise Conflict("A clinician must review the case before consultation notes are recorded.")
    note = ConsultationNote(
        case_id=case.id, doctor_id=payload.doctor_id, consultation_mode=payload.consultation_mode,
        notes=payload.notes, prescription=payload.prescription, follow_up_instructions=payload.follow_up_instructions,
    )
    db.add(note)
    audit.record(db, case.id, f"doctor:{payload.doctor_id}", "consultation.recorded",
                 {"mode": payload.consultation_mode, "has_prescription": bool(payload.prescription), "has_follow_up": bool(payload.follow_up_instructions)})
    db.commit()
    db.refresh(note)
    return serializers.note_out(note)


@router.post("/{case_id}/finalize", response_model=CaseDetailResponse)
async def finalize(case_id: uuid.UUID, db: Session = Depends(get_db)):
    """Hard gate: no patient-facing output before clinician approval and recorded notes."""
    case = case_repo.case_or_404(db, case_id)
    if not case_repo.is_approved(db, case.id):
        raise Conflict("This case has not been approved by a clinician. No visit summary can be released before human review.")
    if not case_repo.notes(db, case.id):
        raise Conflict("Record the consultation notes before finalising the visit.")
    db.close()
    await run_finalize(case_id)
    return serializers.case_detail(db, case_repo.case_or_404(db, case_id))