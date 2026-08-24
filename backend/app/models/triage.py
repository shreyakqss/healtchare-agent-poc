import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid
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