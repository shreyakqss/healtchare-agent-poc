from __future__ import annotations

import hashlib
import math
import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.errors import RateLimited
from app.db import SessionLocal, utcnow
from app.models import RateLimitBucket

POLICIES = {
    "auth.login": (20, 600),
    "auth.callback": (30, 600),
    "auth.self_register": (20, 600),
    "intake.start": (10, 3600),
    "intake.message": (60, 60),
    "attachment.upload": (20, 300),
    "case.prescreen": (10, 600),
    "clinician.verify": (10, 300),
}


def client_identity(request: Request) -> str:
    return request.client.host if request.client else "unknown-client"


def enforce(scope: str, identity: str | uuid.UUID) -> None:
    if not settings.RATE_LIMITING_ENABLED:
        return
    limit, window_seconds = POLICIES[scope]
    now = utcnow()
    reset_before = now - timedelta(seconds=window_seconds)
    key_hash = hashlib.sha256(str(identity).encode()).hexdigest()
    reset_window = RateLimitBucket.window_started_at <= reset_before
    statement = (
        insert(RateLimitBucket)
        .values(
            id=uuid.uuid4(),
            created_at=now,
            scope=scope,
            key_hash=key_hash,
            window_started_at=now,
            request_count=1,
            expires_at=now + timedelta(seconds=window_seconds * 2),
        )
        .on_conflict_do_update(
            constraint="uq_rate_limit_scope_key",
            set_={
                "window_started_at": case((reset_window, now), else_=RateLimitBucket.window_started_at),
                "request_count": case((reset_window, 1), else_=RateLimitBucket.request_count + 1),
                "expires_at": now + timedelta(seconds=window_seconds * 2),
            },
        )
        .returning(RateLimitBucket.request_count, RateLimitBucket.window_started_at)
    )
    with SessionLocal() as db:
        count, window_started_at = db.execute(statement).one()
        db.commit()
    if count > limit:
        elapsed = max(0.0, (now - window_started_at).total_seconds())
        raise RateLimited(max(1, math.ceil(window_seconds - elapsed)))
