from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class TriageRule(Base):
    """An approved administrative triage rule, seeded from config/hospital.yaml.

    These rows are the only thing allowed to set a priority. The LLM explains
    a result; it never produces or overrides one.
    """

    __tablename__ = "triage_rules"

    # Human-readable id shown to clinicians as evidence, e.g. "TR-HIGH-001"
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16), index=True)  # low | medium | high
    # {"any_symptom": [...], "all_symptoms": [...], "min_duration_days": N,
    #  "any_history": [...], "allergy_conflict": true}
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    action: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))
