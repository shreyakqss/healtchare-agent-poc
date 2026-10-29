"""Cases: read, attachments, pre-screening, consultation notes, finalisation.

Routers stay thin: gates and side effects live in `app/services`, the two agno
workflows in `app/workflows`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.agents import AgentUnavailable
from app.api.deps import get_db
from app.api.v1 import serializers
from app.core.config import settings
from app.core.errors import Conflict, Forbidden, NotFound, ServiceUnavailable
from app.domain.lifecycle import CaseStatus
from app.models import MedicalAttachment
from app.schemas.requests import (
    AppointmentSlotRequest,
    AttachmentSkipRequest,
    ConsultationNoteRequest,
    DoctorAssistantRequest,
    FinalizeRequest,
)
from app.schemas.responses import (
    AttachmentResponse,
    AttachmentSkipResponse,
    CaseDetailResponse,
    CaseListItem,
    ConsultationNoteResponse,
    DoctorAssistantResponse,
    PastPatientItem,
    PatientCaseResponse,
    PatientVisitItem,
)
from app.security import (
    CurrentPrincipal,
    case_for_principal,
    cases_for_principal,
    rate_limits,
    require_hms_identity,
    require_roles,
)
from app.services import (
    appointment_service,
    attachment_service,
    attachments,
    case_repo,
    consultation_service,
    doctor_assistant_service,
    past_patients,
    prescreen_trigger,
    workflow_jobs,
)
from app.services.clinician_identity import verify_clinician_async

router = APIRouter(prefix="/cases", tags=["cases"])
PatientPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("patient"))]
ClinicianPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician"))]

PRESCREENABLE = {CaseStatus.INGESTING, CaseStatus.ANALYZING, CaseStatus.FAILED}


@router.get("", response_model=list[CaseListItem])
def list_cases(
    principal: ClinicianPrincipal,
    response: Response,
    # Up to 1000 so the doctor workspace (worklist + calendar) sees the whole clinic in one call.
    limit: int = Query(50, ge=1, le=1000),
    cursor: str | None = Query(None, max_length=256),
    db: Session = Depends(get_db),
):
    page = cases_for_principal(db, principal, "clinician", limit=limit, cursor=cursor)
    if page.next_cursor:
        response.headers["X-Next-Cursor"] = page.next_cursor
    return serializers.listed(serializers.case_list(db, page.items))


@router.get("/past-patients", response_model=list[PastPatientItem])
def list_past_patients(
    principal: ClinicianPrincipal,
    q: str | None = Query(None, max_length=100),
    days: int | None = Query(None, ge=1, le=3650),
    db: Session = Depends(get_db),
):
    """The signed-in doctor's own past patients only, grouped per patient - never the whole
    clinic's. A clinician not linked to a rostered practitioner gets an empty list."""
    me = past_patients.practitioner_id_for(principal.hms_username)
    if me is None:
        return []
    page = cases_for_principal(db, principal, "clinician", limit=past_patients.MAX_CASES_SCANNED)
    return past_patients.group(serializers.listed(serializers.case_list(db, page.items)), doctor_id=me, query=q, days=days)


@router.get("/my-visits", response_model=list[PatientVisitItem])
def list_patient_visits(
    principal: PatientPrincipal,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(None, max_length=256),
    db: Session = Depends(get_db),
):
    page = cases_for_principal(db, principal, "patient", limit=limit, cursor=cursor)
    if page.next_cursor:
        response.headers["X-Next-Cursor"] = page.next_cursor
    return serializers.listed(serializers.patient_case_list(db, page.items))


@router.get("/{case_id}/patient-view", response_model=PatientCaseResponse)
def get_patient_case(case_id: uuid.UUID, principal: PatientPrincipal, db: Session = Depends(get_db)):
    rate_limits.enforce("attachment.upload", principal.user_id)
    case = case_for_principal(db, case_id, principal, allow_clinician=False)
    return serializers.patient_case_detail(db, case)


@router.post("/{case_id}/appointment-slot", response_model=PatientCaseResponse)
def select_appointment_slot(
    case_id: uuid.UUID,
    payload: AppointmentSlotRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
):
    """Patient's pick among the advisory slots offered at routing time. Never a booking - the
    same request goes to the HMS at finalize time regardless of which option was picked."""
    case = case_for_principal(db, case_id, principal, allow_clinician=False)
    appointment_service.select_slot(db, case, payload.slot_id)
    return serializers.patient_case_detail(db, case_repo.case_or_404(db, case_id))


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: uuid.UUID, principal: ClinicianPrincipal, db: Session = Depends(get_db)):
    case = case_for_principal(db, case_id, principal, allow_patient=False)
    return serializers.case_detail(db, case)


@router.post("/{case_id}/attachments", response_model=AttachmentResponse, status_code=201)
async def upload_attachment(
    case_id: uuid.UUID,
    principal: PatientPrincipal,
    file: UploadFile = File(...),
    kind: str = Form("other"),
    uploaded_by: Literal["patient"] = Form("patient"),
    db: Session = Depends(get_db),
):
    """Stored and displayed only. Nothing uploaded here can influence a priority. If this was
    the last thing intake was waiting on, pre-screening starts in the background."""
    case = case_for_principal(db, case_id, principal, allow_clinician=False)
    content = await file.read(settings.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    row = await attachment_service.upload(db, case, file.filename or "upload", content, kind, uploaded_by)
    prescreen_trigger.fire_if_ready(db, case.id)
    return serializers.attachment_out(row)


@router.post("/{case_id}/attachments/skip", response_model=AttachmentSkipResponse)
async def skip_attachment(
    case_id: uuid.UUID,
    payload: AttachmentSkipRequest,
    principal: PatientPrincipal,
    db: Session = Depends(get_db),
):
    """Log that the patient chose not to upload a required document (satisfies the gate)."""
    case = case_for_principal(db, case_id, principal, allow_clinician=False)
    attachment_service.skip(db, case, payload.kind, payload.reason)
    prescreen_trigger.fire_if_ready(db, case.id)
    return AttachmentSkipResponse(ok=True)


@router.get("/{case_id}/attachments/{attachment_id}/file")
def download_attachment(
    case_id: uuid.UUID,
    attachment_id: uuid.UUID,
    principal: Annotated[CurrentPrincipal, Depends(require_roles("patient", "clinician"))],
    db: Session = Depends(get_db),
):
    case_for_principal(db, case_id, principal)
    row = db.get(MedicalAttachment, attachment_id)
    if row is None or row.case_id != case_id:
        raise NotFound("Attachment not found.")
    try:
        path = attachments.absolute_path(row.storage_uri)
    except FileNotFoundError:
        raise NotFound("Stored file is missing.") from None
    if not path.exists():
        raise NotFound("Stored file is missing.")
    # Inline, never a download: the clinician views it in the browser's own viewer.
    return FileResponse(path, media_type=row.mime_type, filename=row.filename, content_disposition_type="inline")


@router.post("/{case_id}/prescreen", response_model=PatientCaseResponse)
async def prescreen(case_id: uuid.UUID, principal: PatientPrincipal, db: Session = Depends(get_db)):
    """Rules -> routing -> briefing. Ends at NEEDS_REVIEW."""
    rate_limits.enforce("case.prescreen", principal.user_id)
    case = case_for_principal(db, case_id, principal, allow_clinician=False)
    session = case_repo.session_for(db, case)
    if session.consent_status != "GRANTED":
        raise Forbidden("Consent must be granted before pre-screening.")
    if session.status not in PRESCREENABLE:
        raise Conflict(f"Pre-screening cannot run while the case is {session.status}.")
    db.close()  # workflow steps open their own sessions
    await workflow_jobs.run_now("prescreen", case_id)
    return serializers.patient_case_detail(db, case_repo.case_or_404(db, case_id))


@router.post("/{case_id}/consultation-notes", response_model=ConsultationNoteResponse, status_code=201)
def add_consultation_note(
    case_id: uuid.UUID,
    payload: ConsultationNoteRequest,
    principal: ClinicianPrincipal,
    db: Session = Depends(get_db),
):
    rate_limits.enforce("clinician.verify", principal.user_id)
    require_hms_identity(principal, payload.doctor_username)
    note = consultation_service.record_note(
        db,
        case_for_principal(db, case_id, principal, allow_patient=False),
        payload,
    )
    return serializers.note_out(note)


@router.post("/{case_id}/finalize", response_model=CaseDetailResponse)
async def finalize(
    case_id: uuid.UUID,
    payload: FinalizeRequest,
    principal: ClinicianPrincipal,
    db: Session = Depends(get_db),
):
    """Hard gate: clinician approval + recorded notes + a verified clinician identity
    (this endpoint triggers HMS writes)."""
    rate_limits.enforce("clinician.verify", principal.user_id)
    require_hms_identity(principal, payload.finalizer_username)
    case = case_for_principal(db, case_id, principal, allow_patient=False)
    consultation_service.assert_finalizable(db, case)
    identity = await verify_clinician_async(payload.finalizer_username, payload.finalizer_password)
    db.close()
    await workflow_jobs.run_now(
        "finalize",
        case_id,
        payload={"finalizer_id": identity.id, "finalizer_name": identity.name},
    )
    return serializers.case_detail(db, case_repo.case_or_404(db, case_id))


@router.post("/{case_id}/assistant", response_model=DoctorAssistantResponse)
async def doctor_assistant_chat(
    case_id: uuid.UUID,
    payload: DoctorAssistantRequest,
    principal: ClinicianPrincipal,
    db: Session = Depends(get_db),
):
    """A clinical assistant for the doctor working this case - discussion only, never a write
    to the record. Not gated behind review/approval: available at any point in the case."""
    rate_limits.enforce("doctor.assistant", principal.user_id)
    case = case_for_principal(db, case_id, principal, allow_patient=False)
    try:
        reply = await doctor_assistant_service.chat(
            db, case.id, payload.doctor_context, payload.message,
            [t.model_dump() for t in payload.transcript],
        )
    except AgentUnavailable as exc:
        raise ServiceUnavailable("The assistant is unavailable right now.") from exc
    return DoctorAssistantResponse(reply=reply)
