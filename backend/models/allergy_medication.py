import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class AllergyMedication(Base):
    __tablename__ = "allergy_medications"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # allergy | medication
    name: Mapped[str] = mapped_column(String(255))
    reaction_or_dose: Mapped[str | None] = mapped_column(Text)
    source_turn: Mapped[int] = mapped_column()
