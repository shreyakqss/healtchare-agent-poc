from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import audit_out
from app.models import AuditEvent
from app.schemas.responses import AuditEventResponse
from app.security import CurrentPrincipal, case_for_principal, require_roles

router = APIRouter(prefix="/cases", tags=["audit"])
ClinicianPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician"))]


@router.get("/{case_id}/audit", response_model=list[AuditEventResponse])
def audit_trail(case_id: uuid.UUID, principal: ClinicianPrincipal, db: Session = Depends(get_db)):
    case_for_principal(db, case_id, principal, allow_patient=False)
    rows = db.query(AuditEvent).filter(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at).all()
    return [audit_out(r) for r in rows]
