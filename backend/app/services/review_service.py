"""Clinician review - the human gate every patient-facing output waits behind.

The doctor reviews by signing the consultation report (consultation_service.record_note records
an `approve` review in the same step), or rejects the case here. Edits go to
`ClinicalReview.edits`; `PatientFact` rows are never rewritten.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ClinicalReview, PatientCase
from app.schemas.requests import ReviewRequest
from app.services import appointment_service, audit, case_repo, lifecycle
from app.services.clinician_identity import VerifiedIdentity, verify_clinician
from app.services.hms import forward_audit_note

REVIEWABLE = {CaseStatus.NEEDS_REVIEW}


def record_review(db: Session, case: PatientCase, payload: ReviewRequest) -> ClinicalReview:
    session = case_repo.session_for(db, case)
    if session.status not in REVIEWABLE:
        raise Conflict(f"A case can only be reviewed once pre-screening has run (status is {session.status}).")

    identity = verify_clinician(payload.reviewer_username, payload.reviewer_password)
    return record_decision(db, case, identity, payload.decision, payload.edits, payload.comment)


def record_decision(
    db: Session, case: PatientCase, identity: VerifiedIdentity, decision: str,
    edits: dict | None = None, comment: str | None = None,
) -> ClinicalReview:
    """The review itself, for a clinician already verified against the HMS. Commits."""
    session = case_repo.session_for(db, case)
    actor = f"clinician:{identity.id}"
    edits = edits or {}
    summary = {"decision": decision, "edited_fields": sorted(edits)}

    review = ClinicalReview(
        case_id=case.id, decision=decision, reviewer_id=identity.id,
        reviewer_role="clinician", edits=edits, comment=comment,
    )
    db.add(review)
    audit.record(db, case.id, actor, "review.recorded", summary)
    target = CaseStatus.REJECTED if decision == "reject" else CaseStatus.APPROVED
    lifecycle.transition(db, session, target, actor, case.id)  # commits
    if target == CaseStatus.REJECTED:
        appointment_service.release_booking(db, case, actor)
    forward_audit_note(case, actor, "review.recorded", summary)
    db.refresh(review)
    return review
