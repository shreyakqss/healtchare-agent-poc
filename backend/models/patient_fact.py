import uuid

from sqlalchemy import Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class PatientFact(Base):
    __tablename__ = "patient_facts"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    # symptom | duration | history | contact_preference | reason_for_visit
    kind: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)
    source_turn: Mapped[int] = mapped_column()
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
