from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AdminAuditEvent, AuditEvent


def record(db: Session, case_id: uuid.UUID, actor: str, action: str, payload: dict[str, Any] | None = None) -> AuditEvent:
    """Append one audit row. Caller commits (keeps the write in the same unit of work)."""
    event = AuditEvent(case_id=case_id, actor=actor, action=action, payload=payload or {})
    db.add(event)
    return event

def record_admin(db: Session, clinic_id: str, actor: str, action: str, payload: dict[str, Any] | None = None) -> AdminAuditEvent:
    """Append one clinic-level admin audit row. Caller commits."""
    event = AdminAuditEvent(clinic_id=clinic_id, actor=actor, action=action, payload=payload or {})
    db.add(event)
    return event
