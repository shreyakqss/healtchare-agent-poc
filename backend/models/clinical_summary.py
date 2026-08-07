import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ClinicalSummary(Base):
    __tablename__ = "clinical_summaries"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), index=True
    )
    # prescreening (before the consultation) | final_visit (after it)
    kind: Mapped[str] = mapped_column(String(32), default="prescreening", index=True)
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    missing_information: Mapped[list[Any]] = mapped_column(JSONB, default=list)
