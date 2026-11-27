import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TriageRule(Base):
    """Approved administrative rule, synced from the hospital YAML.

    These rows are the only thing allowed to set a priority. Scoped by hospital,
    retired rather than deleted so old results still resolve their rule.
    """

    __tablename__ = "triage_rules"
    __table_args__ = (UniqueConstraint("hospital_id", "code", name="uq_rule_per_hospital"),)

    hospital_id: Mapped[str] = mapped_column(String(64), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16), index=True)  # low | medium | high
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    action: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    retired: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class TriageResult(Base):
    __tablename__ = "triage_results"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    priority: Mapped[str] = mapped_column(String(16))
    rule_ids: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    rule_codes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RoutingRecommendation(Base):
    __tablename__ = "routing_recommendations"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    department_id: Mapped[str] = mapped_column(String(64))
    department_name: Mapped[str] = mapped_column(String(128))
    doctor_id: Mapped[str | None] = mapped_column(String(64))
    doctor_name: Mapped[str | None] = mapped_column(String(128))
    appointment_type_id: Mapped[str] = mapped_column(String(64))
    appointment_type_label: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str] = mapped_column(Text)
    matched_keywords: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # Earliest HMS slot found for the department at routing time (advisory only).
    suggested_slot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The open HMS slots offered to the patient at routing time (advisory only).
    slot_options: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    # Which of slot_options the patient picked; None means the earliest (suggested_slot) stands.
    selected_slot_id: Mapped[str | None] = mapped_column(String(64))

class SlotHold(Base):
    """One case's claim on one practitioner time. CareFlow never books in the HMS calendar,
    so this is what keeps two open cases off the same doctor at the same time. The unique
    (practitioner, start) index is the guard; a case holds at most one time. Released when
    the case is rejected; a completed case keeps its time."""

    __tablename__ = "slot_holds"
    __table_args__ = (UniqueConstraint("practitioner_id", "slot_start", name="uq_slot_holds_practitioner_start"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), unique=True
    )
    practitioner_id: Mapped[str] = mapped_column(String(64), index=True)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
