from typing import Any

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class TriageRule(Base):
    """An approved administrative triage rule, seeded from a hospital YAML.

    These rows are the only thing allowed to set a priority. The LLM explains
    a result; it never produces or overrides one.

    Rows are scoped by `hospital_id` and never deleted on a hospital switch, so
    a `TriageResult.rule_ids` written months ago still resolves to the rule text
    that actually fired. Uniqueness is (hospital_id, code) rather than code
    alone — two clinics both numbering a rule TR-HIGH-001 is expected, and
    letting the second overwrite the first would silently rewrite history.
    """

    __tablename__ = "triage_rules"
    __table_args__ = (UniqueConstraint("hospital_id", "code", name="uq_rule_per_hospital"),)

    # Which hospital YAML this rule was seeded from (the file stem).
    hospital_id: Mapped[str] = mapped_column(String(64), index=True)
    # Human-readable id shown to clinicians as evidence, e.g. "TR-HIGH-001"
    code: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16), index=True)  # low | medium | high
    # {"any_symptom": [...], "all_symptoms": [...], "min_duration_days": N,
    #  "any_history": [...], "allergy_conflict": true}
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    action: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))
    # Removed from the YAML but kept as a row: the engine skips retired rules,
    # while a case triaged before the edit still resolves its rule code.
    retired: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
