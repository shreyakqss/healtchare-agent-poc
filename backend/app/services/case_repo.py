"""Read helpers shared by the API and the workflows. Queries only - no writes."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.domain import intake_fields
from app.models import (
    AllergyMedication,
    AuditEvent,
    CareTask,
    ClinicalDiscrepancy,
    ClinicalReview,
    ClinicalSummary,
    ConsultationNote,
    IntakeMessage,
    IntakeSession,
    MedicalAttachment,
    PatientCase,
    PatientFact,
    RoutingRecommendation,
    TriageResult,
)
from app.services import hospital_config


def case_or_404(db: Session, case_id: uuid.UUID) -> PatientCase:
    case = db.get(PatientCase, case_id)
    if case is None:
        raise NotFound("Patient case not found.")
    return case


def session_or_404(db: Session, session_id: uuid.UUID) -> tuple[IntakeSession, PatientCase]:
    session = db.get(IntakeSession, session_id)
    if session is None:
        raise NotFound("Intake session not found.")
    case = db.query(PatientCase).filter(PatientCase.session_id == session.id).first()
    if case is None:
        raise NotFound("Patient case not found.")
    return session, case


def session_for(db: Session, case: PatientCase) -> IntakeSession:
    session = db.get(IntakeSession, case.session_id)
    if session is None:
        raise NotFound("Intake session not found.")
    return session


def messages(db: Session, session_id: uuid.UUID) -> list[IntakeMessage]:
    return (
        db.query(IntakeMessage)
        .filter(IntakeMessage.session_id == session_id)
        .order_by(IntakeMessage.turn_index)
        .all()
    )


def transcript(db: Session, session_id: uuid.UUID) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages(db, session_id)]


def facts(db: Session, case_id: uuid.UUID) -> list[PatientFact]:
    return db.query(PatientFact).filter(PatientFact.case_id == case_id).order_by(PatientFact.source_turn, PatientFact.created_at).all()


def entries(db: Session, case_id: uuid.UUID) -> list[AllergyMedication]:
    return db.query(AllergyMedication).filter(AllergyMedication.case_id == case_id).order_by(AllergyMedication.source_turn).all()


def clinical_entries(db: Session, case_id: uuid.UUID) -> list[AllergyMedication]:
    """Entries minus intake placeholders - a sentinel in both rows would match itself."""
    return [e for e in entries(db, case_id) if e.name not in intake_fields.PLACEHOLDERS]


def attachments(db: Session, case_id: uuid.UUID) -> list[MedicalAttachment]:
    return db.query(MedicalAttachment).filter(MedicalAttachment.case_id == case_id).order_by(MedicalAttachment.created_at).all()


def skipped_attachment_kinds(db: Session, case_id: uuid.UUID) -> set[str]:
    """Required attachment kinds the patient explicitly skipped, from `attachment.skipped`
    audit events - no dedicated table for what is really just a small set membership."""
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.case_id == case_id, AuditEvent.action == "attachment.skipped")
        .all()
    )
    return {row.payload.get("kind") for row in rows if row.payload and row.payload.get("kind")}


def discrepancies(db: Session, case_id: uuid.UUID) -> list[ClinicalDiscrepancy]:
    return (
        db.query(ClinicalDiscrepancy)
        .filter(ClinicalDiscrepancy.case_id == case_id)
        .order_by(ClinicalDiscrepancy.created_at)
        .all()
    )


def latest_triage(db: Session, case_id: uuid.UUID) -> TriageResult | None:
    return db.query(TriageResult).filter(TriageResult.case_id == case_id).order_by(TriageResult.created_at.desc()).first()


def latest_routing(db: Session, case_id: uuid.UUID) -> RoutingRecommendation | None:
    return db.query(RoutingRecommendation).filter(RoutingRecommendation.case_id == case_id).order_by(RoutingRecommendation.created_at.desc()).first()


def latest_review(db: Session, case_id: uuid.UUID) -> ClinicalReview | None:
    return db.query(ClinicalReview).filter(ClinicalReview.case_id == case_id).order_by(ClinicalReview.created_at.desc()).first()


def is_approved(db: Session, case_id: uuid.UUID) -> bool:
    review = latest_review(db, case_id)
    return review is not None and review.decision in {"approve", "edit"}


def summary(db: Session, case_id: uuid.UUID, kind: str) -> ClinicalSummary | None:
    return (
        db.query(ClinicalSummary)
        .filter(ClinicalSummary.case_id == case_id, ClinicalSummary.kind == kind)
        .order_by(ClinicalSummary.created_at.desc())
        .first()
    )


def notes(db: Session, case_id: uuid.UUID) -> list[ConsultationNote]:
    return db.query(ConsultationNote).filter(ConsultationNote.case_id == case_id).order_by(ConsultationNote.created_at).all()


def tasks(db: Session, case_id: uuid.UUID) -> list[CareTask]:
    return db.query(CareTask).filter(CareTask.case_id == case_id).order_by(CareTask.created_at).all()


def missing_fields(db: Session, case_id: uuid.UUID) -> list[str]:
    return intake_fields.missing_fields(
        hospital_config.required_intake_fields(), facts(db, case_id), entries(db, case_id)
    )


def pending_attachment_kinds(db: Session, case_id: uuid.UUID) -> list[str]:
    """Required attachment kinds neither uploaded nor explicitly skipped."""
    required = hospital_config.required_attachment_kinds()
    if not required:
        return []
    uploaded = {a.kind for a in attachments(db, case_id)}
    skipped = skipped_attachment_kinds(db, case_id)
    return [k for k in required if k not in uploaded and k not in skipped]


def ready_for_prescreen(db: Session, case_id: uuid.UUID) -> bool:
    """The intake completeness gate: every required field present AND every required
    attachment kind uploaded or skipped."""
    return not missing_fields(db, case_id) and not pending_attachment_kinds(db, case_id)


# Identity fields are collected by the one-shot form; everything else in
# `required_intake_fields()` is collected by the chat turn loop. Both gates read from the
# SAME hospital-config field list so a hospital that drops a required field (e.g. no
# contact_preference) still needs nothing extra typed anywhere else.
IDENTITY_FIELDS = {"name", "age", "gender", "contact_preference"}


def missing_identity_fields(db: Session, case_id: uuid.UUID) -> list[str]:
    required = [f for f in hospital_config.required_intake_fields() if f in IDENTITY_FIELDS]
    return intake_fields.missing_fields(required, facts(db, case_id), entries(db, case_id))


def missing_clinical_fields(db: Session, case_id: uuid.UUID) -> list[str]:
    required = [f for f in hospital_config.required_intake_fields() if f not in IDENTITY_FIELDS]
    return intake_fields.missing_fields(required, facts(db, case_id), entries(db, case_id))


def next_turn_index(db: Session, session_id: uuid.UUID) -> int:
    return db.query(IntakeMessage).filter(IntakeMessage.session_id == session_id).count()