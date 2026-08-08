import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class IntakeMessage(Base):
    """One turn of the intake conversation.

    `turn_index` is what PatientFact.source_turn points back at, so every
    extracted fact traces to the exact patient statement it came from.
    """

    __tablename__ = "intake_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intake_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # patient | assistant
    content: Mapped[str] = mapped_column(Text)
    turn_index: Mapped[int] = mapped_column(Integer)
    # Which required intake field an assistant question was asking about.
    # Null on patient turns and on anything not asking for a field.
    #
    # This is what lets the next turn tell "the patient said no" from "we never
    # asked": a denial produces no fact, so without it the field looks
    # outstanding forever and gets asked again in different words.
    asks_field: Mapped[str | None] = mapped_column(String(64), default=None)
