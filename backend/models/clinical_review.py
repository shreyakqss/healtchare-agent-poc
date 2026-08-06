import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ClinicalReview(Base):
    __tablename__ = "clinical_reviews"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))  # approve | edit | reject
    reviewer_role: Mapped[str] = mapped_column(String(64))
    # reviewer edits stay separate from the original patient statements
    edits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
