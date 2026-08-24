import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatientCase(Base):
    __tablename__ = "patient_cases"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True, unique=True
    )
    # Display copy of who the patient is: name, age, sex (+ mrn when linked to HMS).
    demographics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # HMS medical record number when intake was started against a known patient.
    hms_patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    hospital_id: Mapped[str] = mapped_column(String(64), index=True)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))