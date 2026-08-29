"""Atomically claim complete intake and enqueue durable pre-screening."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.lifecycle import CaseStatus
from app.models import IntakeSession
from app.services import case_repo, lifecycle, workflow_jobs

ACTOR = "system:prescreen"


def fire_if_ready(db: Session, case_id: uuid.UUID) -> bool:
    case = case_repo.case_or_404(db, case_id)
    session = (
        db.query(IntakeSession)
        .filter(IntakeSession.id == case.session_id)
        .with_for_update()
        .one()
    )
    if session.status != CaseStatus.INGESTING or not case_repo.ready_for_prescreen(db, case_id):
        return False
    lifecycle.transition(db, session, CaseStatus.ANALYZING, ACTOR, case_id, commit=False)
    workflow_jobs.enqueue(db, case_id, "prescreen")
    db.commit()
    return True
