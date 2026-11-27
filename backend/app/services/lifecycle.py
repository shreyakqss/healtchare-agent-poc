"""Status writes go through here so every change is validated and audited."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db import utcnow
from app.domain.lifecycle import TERMINAL, CaseStatus, assert_transition
from app.models import IntakeSession
from app.services import audit, slot_hold_service


def transition(
    db: Session,
    session: IntakeSession,
    target: CaseStatus | str,
    actor: str,
    case_id: uuid.UUID,
    *,
    commit: bool = True,
) -> IntakeSession:
    target = CaseStatus(target)
    assert_transition(session.status, target)
    previous = session.status
    if previous != target:
        session.status = target
        if target in TERMINAL:
            session.completed_at = utcnow()
        audit.record(db, case_id, actor, "status.changed", {"from": previous, "to": target})
        if target in {CaseStatus.REJECTED, CaseStatus.FAILED}:
            # A completed case keeps its time; a failed one re-holds when a retry re-routes it.
            slot_hold_service.release(db, case_id, actor)
    if commit:
        db.commit()
    return session
