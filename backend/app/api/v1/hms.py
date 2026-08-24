"""Read-only window onto the HMS adapter (patients, practitioners, slots, requests)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.errors import NotFound
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import AppointmentRequestResult, HMSPatient, HMSPractitioner, HMSSlot, HMSStatus

router = APIRouter(prefix="/hms", tags=["hms"])


@router.get("/status", response_model=HMSStatus)
def status():
    return get_hms().status()


@router.get("/patients", response_model=list[HMSPatient])
def search_patients(q: str = Query("", max_length=64), limit: int = Query(10, le=50)):
    return get_hms().search_patients(q, limit)


@router.get("/patients/{mrn}", response_model=HMSPatient)
def get_patient(mrn: str):
    patient = get_hms().get_patient(mrn)
    if patient is None:
        raise NotFound(f"No HMS patient with MRN {mrn}.")
    return patient


@router.get("/practitioners", response_model=list[HMSPractitioner])
def practitioners():
    return get_hms().list_practitioners()


@router.get("/slots", response_model=list[HMSSlot])
def slots(department_id: str, practitioner_id: str | None = None, limit: int = Query(5, le=50)):
    return get_hms().available_slots(department_id, practitioner_id, limit)


@router.get("/appointment-requests", response_model=list[AppointmentRequestResult])
def appointment_requests():
    return get_hms().list_requests()