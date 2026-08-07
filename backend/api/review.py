"""Clinician review — the gate every patient-facing output waits behind."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents import human_review
from models import ClinicalReview, PatientCase, get_db
from schemas.request import ReviewRequest
from schemas.response import ReviewResponse

router = APIRouter(prefix="/cases", tags=["review"])


@router.post("/{case_id}/review", response_model=ReviewResponse, status_code=201)
def record_review(
    case_id: uuid.UUID, payload: ReviewRequest, db: Session = Depends(get_db)
):
    """Record approve / edit / reject.

    Edits land in ClinicalReview.edits and never overwrite the original
    patient-reported facts — the two must stay distinguishable.
    """
    case = db.get(PatientCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Patient case not found.")

    try:
        review = human_review.record_review(
            db,
            case.id,
            decision=payload.decision,
            reviewer_role=payload.reviewer_role,
            edits=payload.edits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ReviewResponse(
        id=str(review.id),
        decision=review.decision,
        reviewer_role=review.reviewer_role,
        edits=review.edits or {},
        created_at=review.created_at,
    )


@router.get("/{case_id}/reviews", response_model=list[ReviewResponse])
def list_reviews(case_id: uuid.UUID, db: Session = Depends(get_db)):
    reviews = (
        db.query(ClinicalReview)
        .filter(ClinicalReview.case_id == case_id)
        .order_by(ClinicalReview.created_at)
        .all()
    )
    return [
        ReviewResponse(
            id=str(r.id),
            decision=r.decision,
            reviewer_role=r.reviewer_role,
            edits=r.edits or {},
            created_at=r.created_at,
        )
        for r in reviews
    ]
