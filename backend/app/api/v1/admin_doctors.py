"""Admin > Doctors: list, check, add, and extend the hours of the admin's own hospital's doctors."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.requests import ExtendHoursRequest, NewDoctorRequest
from app.security import CurrentPrincipal, require_roles
from app.services import doctor_onboarding_service as onboarding

router = APIRouter(prefix="/admin/doctors", tags=["admin"])
AdminPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("admin"))]


@router.get("")
def list_doctors(principal: AdminPrincipal):
    clinic = onboarding.clinic_for(principal)
    return {
        # `today` is the clinic's date, the earliest day hours can start.
        "clinic": {"id": clinic.id, "name": clinic.name, "today": clinic.today().isoformat()},
        "doctors": onboarding.list_doctors(clinic),
        "departments": onboarding.specialty_options(clinic),
    }


@router.post("/preview")
def preview(body: NewDoctorRequest, principal: AdminPrincipal):
    """Checks the form against both systems and shows the hours as patients will. Writes nothing."""
    return onboarding.preview(onboarding.clinic_for(principal), body)


@router.post("", status_code=201)
def create(body: NewDoctorRequest, principal: AdminPrincipal, db: Session = Depends(get_db)):
    return onboarding.create(db, principal, body)


@router.post("/{provider_id}/extend-hours")
def extend_hours(provider_id: int, body: ExtendHoursRequest, principal: AdminPrincipal, db: Session = Depends(get_db)):
    return onboarding.extend_hours(db, principal, provider_id, body.weeks)


@router.get("/{provider_id}/removal")
def removal_check(provider_id: int, principal: AdminPrincipal, db: Session = Depends(get_db)):
    """What removing would do (erase if never used, else deactivate) and what blocks it."""
    return onboarding.removal_check(db, principal, provider_id)


@router.delete("/{provider_id}")
def remove(provider_id: int, principal: AdminPrincipal, db: Session = Depends(get_db)):
    return onboarding.remove(db, principal, provider_id)


@router.post("/{provider_id}/reactivate")
def reactivate(provider_id: int, principal: AdminPrincipal, db: Session = Depends(get_db)):
    return onboarding.reactivate(db, principal, provider_id)
