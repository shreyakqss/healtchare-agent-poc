import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IntakeSession(Base):
    """One conversation with the intake assistant. Status follows the case lifecycle."""

    __tablename__ = "intake_sessions"

    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    consent_status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|GRANTED|DECLINED
    channel: Mapped[str] = mapped_column(String(16), default="web")  # web | kiosk | staff
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntakeMessage(Base):
    """One turn. `turn_index` is what PatientFact.source_turn points back at."""

    __tablename__ = "intake_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # patient | assistant
    content: Mapped[str] = mapped_column(Text)
    turn_index: Mapped[int] = mapped_column(Integer)
    # Which required field an assistant question asked about. Lets the next turn
    # tell "patient said no" from "never asked" - a denial writes no fact.
    asks_field: Mapped[str | None] = mapped_column(String(64))