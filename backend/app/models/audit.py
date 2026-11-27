import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    actor: Mapped[str] = mapped_column(String(128))  # patient | system:<agent> | doctor:<id> | staff:<id>
    action: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

class AdminAuditEvent(Base):
    """An administrator's action that belongs to a clinic rather than a patient case, such as
    adding a doctor. Never carries a password."""

    __tablename__ = "admin_audit_events"

    clinic_id: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(128))  # admin:<username>
    action: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
