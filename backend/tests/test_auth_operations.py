import hashlib
import uuid
from datetime import timedelta

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import RateLimited
from app.db import SessionLocal, utcnow
from app.models import ApplicationUser, AuthSession, RateLimitBucket
from app.security import rate_limits
from app.security.sessions import _encrypt, principal_from_session, revoke_user_sessions
from app.services import auth_maintenance


def _request(session_token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [(b"cookie", f"careflow_session={session_token}".encode())],
        }
    )


def test_rate_limit_is_shared_and_stores_only_a_hashed_identity(monkeypatch):
    identity = f"synthetic-client-{uuid.uuid4()}"
    scope = f"test.{uuid.uuid4()}"
    monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
    monkeypatch.setitem(rate_limits.POLICIES, scope, (2, 60))

    rate_limits.enforce(scope, identity)
    rate_limits.enforce(scope, identity)
    with pytest.raises(RateLimited) as raised:
        rate_limits.enforce(scope, identity)

    assert 1 <= raised.value.retry_after <= 60
    with SessionLocal() as db:
        row = db.query(RateLimitBucket).filter(RateLimitBucket.scope == scope).one()
        assert row.request_count == 3
        assert row.key_hash == hashlib.sha256(identity.encode()).hexdigest()
        db.delete(row)
        db.commit()


def test_session_tokens_are_lazily_rewrapped_with_the_active_key(monkeypatch):
    old_key, new_key = "o" * 48, "n" * 48
    monkeypatch.setattr(settings, "AUTH_SESSION_KEYS", {"old": old_key, "new": new_key})
    monkeypatch.setattr(settings, "AUTH_ACTIVE_KEY_ID", "old")
    user_id, raw_session = uuid.uuid4(), f"session-{uuid.uuid4()}"
    with SessionLocal() as db:
        db.add(
            ApplicationUser(
                id=user_id,
                issuer="https://issuer.test/realms/careflow",
                subject=str(user_id),
                roles=["patient"],
                active=True,
            )
        )
        db.add(
            AuthSession(
                token_hash=hashlib.sha256(raw_session.encode()).hexdigest(),
                user_id=user_id,
                csrf_hash="unused",
                encryption_key_id="old",
                access_token_ciphertext=_encrypt("access-token"),
                access_expires_at=utcnow() + timedelta(minutes=5),
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        db.commit()

    monkeypatch.setattr(settings, "AUTH_ACTIVE_KEY_ID", "new")
    with SessionLocal() as db:
        assert principal_from_session(db, _request(raw_session)).user_id == user_id
        row = db.query(AuthSession).filter(AuthSession.user_id == user_id).one()
        assert row.encryption_key_id == "new"
        assert row.access_token_ciphertext.startswith("new$")
        db.delete(db.get(ApplicationUser, user_id))
        db.commit()


def test_auth_maintenance_deletes_only_rows_past_retention(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SESSION_RETENTION_DAYS", 7)
    user_id = uuid.uuid4()
    now = utcnow()
    with SessionLocal() as db:
        db.add(
            ApplicationUser(
                id=user_id,
                issuer="https://issuer.test/realms/careflow",
                subject=str(user_id),
                roles=["patient"],
                active=True,
            )
        )
        db.add(
            AuthSession(
                token_hash=uuid.uuid4().hex,
                user_id=user_id,
                csrf_hash="unused",
                access_token_ciphertext="unused",
                access_expires_at=now - timedelta(days=10),
                expires_at=now - timedelta(days=8),
            )
        )
        db.add(
            RateLimitBucket(
                scope="expired-test",
                key_hash=uuid.uuid4().hex,
                window_started_at=now - timedelta(hours=1),
                expires_at=now - timedelta(seconds=1),
            )
        )
        db.commit()

    assert auth_maintenance.cleanup() == (1, 1)
    with SessionLocal() as db:
        db.delete(db.get(ApplicationUser, user_id))
        db.commit()


def test_administrator_can_revoke_all_active_user_sessions():
    user_id = uuid.uuid4()
    now = utcnow()
    with SessionLocal() as db:
        db.add(
            ApplicationUser(
                id=user_id,
                issuer="https://issuer.test/realms/careflow",
                subject=str(user_id),
                roles=["patient"],
                active=True,
            )
        )
        for _ in range(2):
            db.add(
                AuthSession(
                    token_hash=uuid.uuid4().hex,
                    user_id=user_id,
                    csrf_hash="unused",
                    access_token_ciphertext="unused",
                    access_expires_at=now + timedelta(minutes=5),
                    expires_at=now + timedelta(hours=1),
                )
            )
        db.commit()
        assert revoke_user_sessions(db, user_id) == 2
        assert all(row.revoked_at is not None for row in db.query(AuthSession).filter_by(user_id=user_id))
        db.delete(db.get(ApplicationUser, user_id))
        db.commit()
