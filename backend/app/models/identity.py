import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ApplicationUser(Base):
    __tablename__ = "application_users"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_application_user_identity"),)

    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255), index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    hms_username: Mapped[str | None] = mapped_column(String(64))
    hms_patient_id: Mapped[str | None] = mapped_column(String(64))
    roles: Mapped[list[str]] = mapped_column(JSONB, default=list)
    clinic_id: Mapped[str | None] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("application_users.id", ondelete="CASCADE"), index=True
    )
    csrf_hash: Mapped[str] = mapped_column(String(64))
    encryption_key_id: Mapped[str] = mapped_column(String(32), default="legacy", server_default="legacy")
    client_id: Mapped[str] = mapped_column(String(255), default="careflow-web", server_default="careflow-web")
    access_token_ciphertext: Mapped[str] = mapped_column(Text)
    refresh_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    id_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class CaseOwner(Base):
    __tablename__ = "case_owners"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patient_cases.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("application_users.id", ondelete="RESTRICT"), index=True
    )


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (UniqueConstraint("scope", "key_hash", name="uq_rate_limit_scope_key"),)

    scope: Mapped[str] = mapped_column(String(64))
    key_hash: Mapped[str] = mapped_column(String(64))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
