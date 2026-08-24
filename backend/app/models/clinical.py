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


class ConsultationNote(Base):
    """Authored by a clinician, never by an agent."""

    __tablename__ = "consultation_notes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    doctor_id: Mapped[str] = mapped_column(String(64))
    consultation_mode: Mapped[str] = mapped_column(String(16), default="in_person")
    notes: Mapped[str] = mapped_column(Text)
    prescription: Mapped[str | None] = mapped_column(Text)
    follow_up_instructions: Mapped[str | None] = mapped_column(Text)