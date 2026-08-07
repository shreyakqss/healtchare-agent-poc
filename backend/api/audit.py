"""Audit timeline — every consent, status change, and decision on a case."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models import AuditEvent, get_db
from schemas.response import AuditEventResponse

router = APIRouter(prefix="/cases", tags=["audit"])


@router.get("/{case_id}/audit", response_model=list[AuditEventResponse])
def get_audit_trail(case_id: uuid.UUID, db: Session = Depends(get_db)):
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.created_at)
        .all()
    )
    return [
        AuditEventResponse(
            id=str(e.id),
            actor=e.actor,
            action=e.action,
            payload=e.payload or {},
            created_at=e.created_at,
        )
        for e in events
    ]
