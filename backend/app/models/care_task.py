import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CareTask(Base):
    """Draft scheduling / escalation task created after clinician review.

    Always `status = draft`. The HMS adapter receives an appointment *request*,
    never a confirmed booking - real booking is out of scope.
    """

    __tablename__ = "care_tasks"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    task_type: Mapped[str] = mapped_column(String(32))  # schedule_appointment | escalate | follow_up
    status: Mapped[str] = mapped_column(String(16), default="draft")
    priority: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    hms_reference: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)