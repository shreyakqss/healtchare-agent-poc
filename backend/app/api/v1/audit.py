from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import audit_out
from app.models import AuditEvent
from app.schemas.responses import AuditEventResponse
from app.services import case_repo

router = APIRouter(prefix="/cases", tags=["audit"])


@router.get("/{case_id}/audit", response_model=list[AuditEventResponse])
def audit_trail(case_id: uuid.UUID, db: Session = Depends(get_db)):
    case_repo.case_or_404(db, case_id)
    rows = db.query(AuditEvent).filter(AuditEvent.case_id == case_id).order_by(AuditEvent.created_at).all()
    return [audit_out(r) for r in rows]