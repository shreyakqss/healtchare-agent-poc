"""Clinician review - the human gate every patient-facing output waits behind.

Edits go to `ClinicalReview.edits`; `PatientFact` rows are never rewritten.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ClinicalReview, PatientCase
from app.schemas.requests import ReviewRequest
from app.services import audit, case_repo, lifecycle
from app.services.clinician_identity import verify_clinician
from app.services.hms import forward_audit_note

REVIEWABLE = {CaseStatus.NEEDS_REVIEW}


def record_review(db: Session, case: PatientCase, payload: ReviewRequest) -> ClinicalReview:
    session = case_repo.session_for(db, case)
    if session.status not in REVIEWABLE:
        raise Conflict(f"A case can only be reviewed once pre-screening has run (status is {session.status}).")

    identity = verify_clinician(payload.reviewer_username, payload.reviewer_password)
    actor = f"clinician:{identity.id}"
    summary = {"decision": payload.decision, "edited_fields": sorted(payload.edits)}

    review = ClinicalReview(
        case_id=case.id, decision=payload.decision, reviewer_id=identity.id,
        reviewer_role="clinician", edits=payload.edits, comment=payload.comment,
    )
    db.add(review)
    audit.record(db, case.id, actor, "review.recorded", summary)
    target = CaseStatus.REJECTED if payload.decision == "reject" else CaseStatus.APPROVED
    lifecycle.transition(db, session, target, actor, case.id)  # commits
    forward_audit_note(case, actor, "review.recorded", summary)
    db.refresh(review)
    return review
