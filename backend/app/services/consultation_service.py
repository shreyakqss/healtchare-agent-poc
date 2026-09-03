"""Consultation notes and the finalisation gate. Both sit behind clinician approval."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ConsultationNote, PatientCase
from app.schemas.requests import ConsultationNoteRequest
from app.services import audit, case_repo
from app.services.clinician_identity import verify_clinician

NOT_APPROVED_FOR_NOTES = "A clinician must review the case before consultation notes are recorded."
NOT_APPROVED_FOR_FINALIZE = (
    "This case has not been approved by a clinician. No visit summary can be released before human review."
)
NOTES_REQUIRED = "Record the consultation notes before finalising the visit."


def record_note(db: Session, case: PatientCase, payload: ConsultationNoteRequest) -> ConsultationNote:
    if not case_repo.is_approved(db, case.id):
        raise Conflict(NOT_APPROVED_FOR_NOTES)
    identity = verify_clinician(payload.doctor_username, payload.doctor_password)
    note = ConsultationNote(
        case_id=case.id, doctor_id=identity.id, doctor_name=identity.name,
        consultation_mode=payload.consultation_mode, notes=payload.notes,
        prescription=payload.prescription, follow_up_instructions=payload.follow_up_instructions,
        tests_ordered=payload.tests_ordered, referral_notes=payload.referral_notes,
        patient_report=payload.patient_report,
    )
    db.add(note)
    audit.record(db, case.id, f"doctor:{identity.id}", "consultation.recorded", {
        "mode": payload.consultation_mode,
        "has_prescription": bool(payload.prescription),
        "has_follow_up": bool(payload.follow_up_instructions),
    })
    db.commit()
    db.refresh(note)
    return note


def assert_finalizable(db: Session, case: PatientCase) -> None:
    """Hard gate: approval and recorded notes before any patient-facing output."""
    session = case_repo.session_for(db, case)
    if session.status != CaseStatus.APPROVED:
        raise Conflict(f"Only an approved case can be finalised (status is {session.status}).")
    if not case_repo.is_approved(db, case.id):
        raise Conflict(NOT_APPROVED_FOR_FINALIZE)
    if not case_repo.notes(db, case.id):
        raise Conflict(NOTES_REQUIRED)
