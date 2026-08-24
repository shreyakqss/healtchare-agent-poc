from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(db: Session, case_id: uuid.UUID, actor: str, action: str, payload: dict[str, Any] | None = None) -> AuditEvent:
    """Append one audit row. Caller commits (keeps the write in the same unit of work)."""
    event = AuditEvent(case_id=case_id, actor=actor, action=action, payload=payload or {})
    db.add(event)
    return event