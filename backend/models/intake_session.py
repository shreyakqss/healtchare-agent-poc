from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class IntakeSession(Base):
    __tablename__ = "intake_sessions"

    # CREATED | INGESTING | ANALYZING | NEEDS_REVIEW | APPROVED | COMPLETED | REJECTED | FAILED
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    # PENDING | GRANTED | DECLINED
    consent_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
