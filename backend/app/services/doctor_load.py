"""How many open cases each doctor carries: the tie-break when two doctors share the earliest
free time, and what blocks removing a doctor in Admin > Doctors."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import IntakeSession, PatientCase, RoutingRecommendation

CLOSED_STATUSES = {"COMPLETED", "REJECTED", "FAILED"}


def open_case_counts(
    db: Session, practitioner_ids: list[str], excluding_case: uuid.UUID | None = None
) -> dict[str, int]:
    """`{practitioner id: open cases}`. A case counts for the doctor its latest routing names,
    while it is not completed, rejected or failed. Doctors with none are absent."""
    if not practitioner_ids:
        return {}
    latest = (
        db.query(RoutingRecommendation.case_id, RoutingRecommendation.doctor_id)
        .order_by(RoutingRecommendation.case_id, RoutingRecommendation.created_at.desc())
        .distinct(RoutingRecommendation.case_id)
        .subquery()
    )
    query = (
        db.query(latest.c.doctor_id, func.count())
        .join(PatientCase, PatientCase.id == latest.c.case_id)
        .join(IntakeSession, IntakeSession.id == PatientCase.session_id)
        .filter(latest.c.doctor_id.in_(practitioner_ids), IntakeSession.status.notin_(CLOSED_STATUSES))
    )
    if excluding_case is not None:
        query = query.filter(latest.c.case_id != excluding_case)
    return dict(query.group_by(latest.c.doctor_id).all())
