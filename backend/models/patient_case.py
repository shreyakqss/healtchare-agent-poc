import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class PatientCase(Base):
    __tablename__ = "patient_cases"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True
    )
    demographics_fixture: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    specialty_hint: Mapped[str | None] = mapped_column(String(128))
