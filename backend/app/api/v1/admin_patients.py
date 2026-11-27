"""Admin > Patients: the admin's own clinic's patient directory. Administrative fields only;
it never opens a case (admin alone never grants clinical access)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1 import serializers
from app.core.errors import Forbidden
from app.models import PatientCase
from app.schemas.responses import AdminPatientItem
from app.security import CurrentPrincipal, require_roles
from app.services import patient_directory

router = APIRouter(prefix="/admin/patients", tags=["admin"])
AdminPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("admin"))]

# Enough for a clinic POC; newest cases first.
MAX_CASES = 1000


@router.get("", response_model=list[AdminPatientItem])
def list_patients(principal: AdminPrincipal, db: Session = Depends(get_db)):
    if not principal.clinic_id:
        raise Forbidden("This admin login is not linked to a hospital.")
    cases = (
        db.query(PatientCase).filter(PatientCase.hospital_id == principal.clinic_id)
        .order_by(PatientCase.created_at.desc()).limit(MAX_CASES).all()
    )
    return patient_directory.build(serializers.listed(serializers.case_list(db, cases)))
