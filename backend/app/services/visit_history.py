"""Follow-up visits: which of a patient's own visits can be followed up, and what the follow-up
carries over from it.

A follow-up is about the problem of one completed visit of the same account. It is routed to that
visit's department with that visit's doctor offered first (the patient may still pick another of the
department's doctors); intake asks about how the problem has gone since; the doctor sees the
previous diagnosis, prescription and advice. Only what the doctor signed and released is carried
over - the same report the patient already has - never the AI differential or referral notes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import CaseOwner, IntakeSession, PatientCase
from app.services import case_repo

VISIT_TYPES = ("new", "follow_up")


@dataclass(frozen=True)
class PreviousVisit:
    case_id: str
    visit_at: datetime
    department_id: str | None
    department_name: str | None
    doctor_id: str | None
    doctor_name: str | None
    complaint: str | None
    diagnosis: str | None
    prescription: str | None
    tests: str | None
    advice: str | None


def _complaint(db: Session, case_id: uuid.UUID) -> str | None:
    values = [f.value for f in case_repo.facts(db, case_id) if f.kind == "reason_for_visit"]
    return ", ".join(dict.fromkeys(values)) or None


def summarize(db: Session, case: PatientCase) -> PreviousVisit:
    notes = case_repo.notes(db, case.id)
    note = notes[-1] if notes else None
    routing = case_repo.latest_routing(db, case.id)
    return PreviousVisit(
        case_id=str(case.id),
        visit_at=note.created_at if note else case.created_at,
        department_id=routing.department_id if routing else None,
        department_name=routing.department_name if routing else None,
        doctor_id=routing.doctor_id if routing else None,
        doctor_name=(note.doctor_name if note and note.doctor_name else None) or (routing.doctor_name if routing else None),
        complaint=_complaint(db, case.id),
        diagnosis=note.diagnosis if note else None,
        prescription=note.prescription if note else None,
        tests=note.tests_ordered if note else None,
        advice=note.follow_up_instructions if note else None,
    )


def _completed(db: Session, owner_user_id: uuid.UUID):
    return (
        db.query(PatientCase)
        .join(CaseOwner, CaseOwner.case_id == PatientCase.id)
        .join(IntakeSession, IntakeSession.id == PatientCase.session_id)
        .filter(CaseOwner.user_id == owner_user_id, IntakeSession.status == "COMPLETED")
    )


def follow_up_options(db: Session, owner_user_id: uuid.UUID, limit: int = 20) -> list[PreviousVisit]:
    """The account's own completed visits, newest first - what a follow-up may be about."""
    cases = _completed(db, owner_user_id).order_by(PatientCase.created_at.desc()).limit(limit).all()
    return sorted((summarize(db, c) for c in cases), key=lambda v: v.visit_at, reverse=True)


def parent_for(db: Session, owner_user_id: uuid.UUID, case_id: uuid.UUID) -> PatientCase:
    """The visit a new follow-up is about: one of this account's own completed visits, or 409."""
    parent = _completed(db, owner_user_id).filter(PatientCase.id == case_id).one_or_none()
    if parent is None:
        raise Conflict("A follow-up can only be about one of your own completed visits.")
    return parent


def previous_visit(db: Session, case: PatientCase) -> PreviousVisit | None:
    if case.visit_type != "follow_up" or case.follow_up_of is None:
        return None
    parent = db.get(PatientCase, case.follow_up_of)
    return summarize(db, parent) if parent is not None else None


def _lines(visit: PreviousVisit) -> list[str]:
    lines = [f"Visit on {visit.visit_at:%Y-%m-%d}"
             + (f" ({visit.department_name}" + (f", {visit.doctor_name}" if visit.doctor_name else "") + ")"
                if visit.department_name else "")]
    for label, value in (("Complaint then", visit.complaint), ("Diagnosis", visit.diagnosis),
                         ("Prescription", visit.prescription), ("Tests advised", visit.tests),
                         ("Advice given", visit.advice)):
        if value and value.strip():
            lines.append(f"{label}: {' / '.join(x.strip() for x in value.splitlines() if x.strip())}")
    return lines


def context_text(visit: PreviousVisit) -> str:
    """Plain lines for the intake planner and the clinician-facing agents."""
    return "\n".join(_lines(visit))
