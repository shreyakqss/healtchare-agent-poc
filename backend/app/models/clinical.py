import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClinicalSummary(Base):
    __tablename__ = "clinical_summaries"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)  # prescreening | final_visit
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    generated_by: Mapped[str] = mapped_column(String(32), default="llm")  # llm | fallback


class ClinicalReview(Base):
    """The human gate. Edits live here and never overwrite PatientFact rows."""

    __tablename__ = "clinical_reviews"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))  # approve | edit | reject
    reviewer_id: Mapped[str] = mapped_column(String(64))
    reviewer_role: Mapped[str] = mapped_column(String(64))
    edits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    comment: Mapped[str | None] = mapped_column(Text)


class ClinicalDiscrepancy(Base):
    """Clinician-facing flag from the discrepancy-checker agent: patient statement vs. document/HMS
    record. Advisory only - never read by triage_engine.evaluate() and never shown to the patient."""

    __tablename__ = "clinical_discrepancies"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    field_or_topic: Mapped[str] = mapped_column(String(255))
    patient_stated: Mapped[str] = mapped_column(Text)
    document_says: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(16))  # document | hms
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("medical_attachments.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(16))  # info | review
    requested_document_kind: Mapped[str | None] = mapped_column(String(64))
    generated_by: Mapped[str] = mapped_column(String(32), default="llm")  # llm | fallback


class ConsultationNote(Base):
    """Authored by a clinician, never by an agent."""

    __tablename__ = "consultation_notes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    doctor_id: Mapped[str] = mapped_column(String(64))
    # Captured at write-time from the verified HMS identity (identity.name). doctor_id is now
    # a real hospital-system identifier (an OpenEMR Practitioner UUID) rather than a local
    # hospital_config.yaml doctor id, so it can no longer be resolved to a display name via
    # hospital_config.doctor_by_id() - that lookup only knows the configured fallback roster.
    doctor_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consultation_mode: Mapped[str] = mapped_column(String(16), default="in_person")
    notes: Mapped[str] = mapped_column(Text)
    prescription: Mapped[str | None] = mapped_column(Text)
    follow_up_instructions: Mapped[str | None] = mapped_column(Text)
    tests_ordered: Mapped[str | None] = mapped_column(Text)
    # For other clinicians on referral, never surfaced on the patient-facing summary or the
    # patient endpoint's safe projection (see finalize.py: not written into ClinicalSummary.sections).
    referral_notes: Mapped[str | None] = mapped_column(Text)
    # The doctor's own final-draft report to the patient, in their own words. When set, this
    # stands in for the model-drafted patient_friendly_summary at finalize time.
    patient_report: Mapped[str | None] = mapped_column(Text)