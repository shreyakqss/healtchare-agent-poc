from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import or_

from app.core.config import settings
from app.db import SessionLocal, utcnow
from app.models import AuthSession, RateLimitBucket


def cleanup(batch_size: int = 1000) -> tuple[int, int]:
    now = utcnow()
    session_cutoff = now - timedelta(days=settings.AUTH_SESSION_RETENTION_DAYS)
    with SessionLocal() as db:
        session_ids = [
            row[0]
            for row in (
                db.query(AuthSession.id)
                .filter(
                    or_(
                        AuthSession.expires_at < session_cutoff,
                        AuthSession.revoked_at < session_cutoff,
                    )
                )
                .limit(batch_size)
                .all()
            )
        ]
        expired_bucket_ids = [
            row[0]
            for row in (
                db.query(RateLimitBucket.id)
                .filter(RateLimitBucket.expires_at < now)
                .limit(batch_size)
                .all()
            )
        ]
        sessions_deleted = (
            db.query(AuthSession)
            .filter(AuthSession.id.in_(session_ids))
            .delete(synchronize_session=False)
            if session_ids
            else 0
        )
        buckets_deleted = (
            db.query(RateLimitBucket)
            .filter(RateLimitBucket.id.in_(expired_bucket_ids))
            .delete(synchronize_session=False)
            if expired_bucket_ids
            else 0
        )
        db.commit()
    return sessions_deleted, buckets_deleted


async def run_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        await asyncio.to_thread(cleanup)
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.AUTH_MAINTENANCE_SECONDS)
        except TimeoutError:
            pass
