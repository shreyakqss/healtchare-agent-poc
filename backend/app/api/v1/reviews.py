"""Clinician review - the gate every patient-facing output waits behind."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import review_out
from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ClinicalReview
from app.schemas.requests import ReviewRequest
from app.schemas.responses import ReviewResponse
from app.services import audit, case_repo, lifecycle

router = APIRouter(prefix="/cases", tags=["review"])


@router.post("/{case_id}/review", response_model=ReviewResponse, status_code=201)
def record_review(case_id: uuid.UUID, payload: ReviewRequest, db: Session = Depends(get_db)):
    """Edits go to ClinicalReview.edits; PatientFact rows are never rewritten."""
    case = case_repo.case_or_404(db, case_id)
    session = case_repo.session_for(db, case)
    if session.status not in {CaseStatus.NEEDS_REVIEW, CaseStatus.APPROVED}:
        raise Conflict(f"A case can only be reviewed once pre-screening has run (status is {session.status}).")

    review = ClinicalReview(
        case_id=case.id, decision=payload.decision, reviewer_id=payload.reviewer_id,
        reviewer_role=payload.reviewer_role, edits=payload.edits, comment=payload.comment,
    )
    db.add(review)
    audit.record(db, case.id, f"{payload.reviewer_role}:{payload.reviewer_id}", "review.recorded",
                 {"decision": payload.decision, "edited_fields": sorted(payload.edits)})
    target = CaseStatus.REJECTED if payload.decision == "reject" else CaseStatus.APPROVED
    lifecycle.transition(db, session, target, f"{payload.reviewer_role}:{payload.reviewer_id}", case.id)
    db.refresh(review)
    return review_out(review)


@router.get("/{case_id}/reviews", response_model=list[ReviewResponse])
def list_reviews(case_id: uuid.UUID, db: Session = Depends(get_db)):
    case_repo.case_or_404(db, case_id)
    rows = db.query(ClinicalReview).filter(ClinicalReview.case_id == case_id).order_by(ClinicalReview.created_at).all()
    return [review_out(r) for r in rows]