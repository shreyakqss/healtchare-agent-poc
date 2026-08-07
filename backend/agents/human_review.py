"""Human Review — records the clinician's approve / edit / reject decision.

The gate the whole POC turns on. No LLM involvement, and critically: reviewer
edits are written to `ClinicalReview.edits` and never applied over the original
`PatientFact` rows, so what the patient said stays distinguishable from what a
clinician corrected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import AuditEvent, ClinicalReview, IntakeSession, PatientCase

VALID_DECISIONS = {"approve", "edit", "reject"}


def latest_review(db: Session, case_id) -> ClinicalReview | None:
    return (
        db.query(ClinicalReview)
        .filter(ClinicalReview.case_id == case_id)
        .order_by(ClinicalReview.created_at.desc())
        .first()
    )


def is_approved(db: Session, case_id) -> bool:
    """True only when a clinician has actively approved or approved-with-edits."""
    review = latest_review(db, case_id)
    return review is not None and review.decision in {"approve", "edit"}


def record_review(
    db: Session,
    case_id,
    decision: str,
    reviewer_role: str,
    edits: dict | None = None,
) -> ClinicalReview:
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Unknown review decision '{decision}'. "
            f"Expected one of: {', '.join(sorted(VALID_DECISIONS))}."
        )

    review = ClinicalReview(
        case_id=case_id,
        decision=decision,
        reviewer_role=reviewer_role,
        # Kept separate from PatientFact on purpose — see module docstring.
        edits=edits or {},
    )
    db.add(review)

    case = db.get(PatientCase, case_id)
    if case is not None:
        session = db.get(IntakeSession, case.session_id)
        if session is not None:
            if decision == "reject":
                session.status = "REJECTED"
                session.completed_at = datetime.now(timezone.utc)
            else:
                session.status = "APPROVED"

    db.add(
        AuditEvent(
            case_id=case_id,
            actor=f"clinician:{reviewer_role}",
            action="review.recorded",
            payload={
                "decision": decision,
                "edited_fields": sorted((edits or {}).keys()),
            },
        )
    )
    db.commit()
    db.refresh(review)
    return review
