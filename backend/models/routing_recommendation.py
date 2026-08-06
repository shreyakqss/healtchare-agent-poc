import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class RoutingRecommendation(Base):
    __tablename__ = "routing_recommendations"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    specialty: Mapped[str] = mapped_column(String(128))
    appointment_type: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str] = mapped_column(Text)
