"""Clinician review - the gate every patient-facing output waits behind."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.v1.serializers import review_out
from app.models import ClinicalReview
from app.schemas.requests import ReviewRequest
from app.schemas.responses import ReviewResponse
from app.security import CurrentPrincipal, case_for_principal, rate_limits, require_hms_identity, require_roles
from app.services import review_service

router = APIRouter(prefix="/cases", tags=["review"])
ClinicianPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician"))]


@router.post("/{case_id}/review", response_model=ReviewResponse, status_code=201)
def record_review(
    case_id: uuid.UUID,
    payload: ReviewRequest,
    principal: ClinicianPrincipal,
    db: Session = Depends(get_db),
):
    """Edits go to ClinicalReview.edits; PatientFact rows are never rewritten."""
    rate_limits.enforce("clinician.verify", principal.user_id)
    require_hms_identity(principal, payload.reviewer_username)
    review = review_service.record_review(
        db,
        case_for_principal(db, case_id, principal, allow_patient=False),
        payload,
    )
    return review_out(review)


@router.get("/{case_id}/reviews", response_model=list[ReviewResponse])
def list_reviews(case_id: uuid.UUID, principal: ClinicianPrincipal, db: Session = Depends(get_db)):
    case_for_principal(db, case_id, principal, allow_patient=False)
    rows = db.query(ClinicalReview).filter(ClinicalReview.case_id == case_id).order_by(ClinicalReview.created_at).all()
    return [review_out(r) for r in rows]
