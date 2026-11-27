"""Consultation notes and the finalisation gate. Both sit behind clinician approval."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.domain.lifecycle import CaseStatus
from app.models import ConsultationNote, PatientCase
from app.schemas.requests import ConsultationNoteRequest
from app.services import audit, case_repo, review_service
from app.services.clinician_identity import verify_clinician

NOT_APPROVED_FOR_NOTES = "A clinician must review the case before consultation notes are recorded."
NOT_APPROVED_FOR_FINALIZE = (
    "This case has not been approved by a clinician. No visit summary can be released before human review."
)
NOTES_REQUIRED = "Record the consultation notes before finalising the visit."
REPORT_RELEASED = "The visit summary has been released; the consultation report is final."


def record_note(db: Session, case: PatientCase, payload: ConsultationNoteRequest) -> ConsultationNote:
    """Every save is a new version - earlier ones are kept, the latest is the report. Signing
    the first report on a case awaiting review is the doctor's review: it records an `approve`
    ClinicalReview with the same verified identity, so a signed review exists before any note.
    Once the visit summary is released the report is final and can no longer be changed."""
    if case_repo.session_for(db, case).status == CaseStatus.COMPLETED:
        raise Conflict(REPORT_RELEASED)
    awaiting_review = case_repo.session_for(db, case).status in review_service.REVIEWABLE
    if not awaiting_review and not case_repo.is_approved(db, case.id):
        raise Conflict(NOT_APPROVED_FOR_NOTES)
    identity = verify_clinician(payload.doctor_username, payload.doctor_password)
    if awaiting_review:
        review_service.record_decision(db, case, identity, "approve", comment="Reviewed by signing the consultation report.")
    version = len(case_repo.notes(db, case.id)) + 1
    note = ConsultationNote(
        case_id=case.id, doctor_id=identity.id, doctor_name=identity.name,
        consultation_mode=payload.consultation_mode, notes=payload.notes,
        prescription=payload.prescription, follow_up_instructions=payload.follow_up_instructions,
        tests_ordered=payload.tests_ordered, referral_notes=payload.referral_notes,
        patient_report=payload.patient_report, diagnosis=payload.diagnosis,
    )
    db.add(note)
    audit.record(db, case.id, f"doctor:{identity.id}", "consultation.recorded", {
        "mode": payload.consultation_mode,
        "version": version,
        "has_prescription": bool(payload.prescription),
        "has_follow_up": bool(payload.follow_up_instructions),
        "ai_drafted_sections": sorted(set(payload.ai_drafted_sections)),
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
