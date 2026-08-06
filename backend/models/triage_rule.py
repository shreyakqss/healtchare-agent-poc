from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class TriageRule(Base):
    __tablename__ = "triage_rules"

    version: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16), index=True)  # low | medium | high
    condition: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
