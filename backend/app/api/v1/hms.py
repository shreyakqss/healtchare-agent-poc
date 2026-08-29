"""Read-only window onto the HMS adapter (patients, practitioners, slots, requests)."""

from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.errors import NotFound
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import (
    AppointmentRequestResult,
    HMSDocument,
    HMSPatient,
    HMSPractitioner,
    HMSSlot,
    HMSStatus,
)
from app.security import CurrentPrincipal, require_active_clinic, require_roles

router = APIRouter(prefix="/hms", tags=["hms"])
StaffPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician", "admin"))]
ClinicianPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician"))]


def _require_clinician_clinic(principal: ClinicianPrincipal) -> None:
    require_active_clinic(principal)


@router.get("/status", response_model=HMSStatus)
def status(_: StaffPrincipal):
    return get_hms().status()


@router.get("/patients", response_model=list[HMSPatient])
def search_patients(
    principal: ClinicianPrincipal,
    q: str = Query("", min_length=2, max_length=64),
    limit: int = Query(10, le=50),
):
    _require_clinician_clinic(principal)
    return get_hms().search_patients(q, limit)


@router.get("/patients/{mrn}", response_model=HMSPatient)
def get_patient(mrn: str, principal: ClinicianPrincipal):
    _require_clinician_clinic(principal)
    patient = get_hms().get_patient(mrn)
    if patient is None:
        raise NotFound(f"No HMS patient with MRN {mrn}.")
    return patient


@router.get("/patients/{mrn}/documents", response_model=list[HMSDocument])
def patient_documents(mrn: str, principal: ClinicianPrincipal, limit: int = Query(20, le=50)):
    _require_clinician_clinic(principal)
    if get_hms().get_patient(mrn) is None:
        raise NotFound(f"No HMS patient with MRN {mrn}.")
    return get_hms().list_documents(mrn, limit)


@router.get("/patients/{mrn}/documents/{reference}/file")
def patient_document_file(mrn: str, reference: str, principal: ClinicianPrincipal):
    """Proxy a linked OpenEMR document; browser clients never receive HMS credentials."""
    _require_clinician_clinic(principal)
    try:
        content, mime_type, title = get_hms().get_document_content(mrn, reference)
    except (FileNotFoundError, PermissionError):
        raise NotFound("Document not found.") from None
    safe_type = mime_type if re.fullmatch(r"[\w.+-]+/[\w.+-]+", mime_type) else "application/octet-stream"
    safe_title = title.replace("\r", "").replace("\n", "").strip() or "document"
    disposition = f"inline; filename*=UTF-8''{quote(safe_title, safe='')}"
    return Response(content=content, media_type=safe_type, headers={"Content-Disposition": disposition})


@router.get("/practitioners", response_model=list[HMSPractitioner])
def practitioners(principal: ClinicianPrincipal, limit: int = Query(50, ge=1, le=100)):
    _require_clinician_clinic(principal)
    return get_hms().list_practitioners(limit=limit)


@router.get("/slots", response_model=list[HMSSlot])
def slots(
    department_id: str,
    principal: ClinicianPrincipal,
    practitioner_id: str | None = None,
    limit: int = Query(5, le=50),
):
    _require_clinician_clinic(principal)
    return get_hms().available_slots(department_id, practitioner_id, limit)


@router.get("/appointment-requests", response_model=list[AppointmentRequestResult])
def appointment_requests(principal: ClinicianPrincipal, limit: int = Query(50, ge=1, le=100)):
    _require_clinician_clinic(principal)
    return get_hms().list_requests(limit=limit)
