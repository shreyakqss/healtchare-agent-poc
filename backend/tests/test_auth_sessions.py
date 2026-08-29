import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import Forbidden
from app.db import SessionLocal
from app.models import ApplicationUser, AuthSession
from app.security.authorization import require_hms_identity
from app.security.oidc import CurrentPrincipal
from app.security.sessions import _decode_transaction, authorization_request, principal_from_session


def _request(method: str, cookie: str, csrf: str | None = None) -> Request:
    headers = [(b"cookie", cookie.encode())]
    if csrf:
        headers.append((b"x-csrf-token", csrf.encode()))
    return Request({"type": "http", "method": method, "headers": headers})


def test_authorization_request_uses_pkce_and_rejects_external_return(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SESSION_SECRET", "test-secret-that-is-at-least-thirty-two-bytes")
    location, transaction = authorization_request("https://attacker.example/steal")
    query = parse_qs(urlsplit(location).query)
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] and query["state"] and transaction
    assert _decode_transaction(transaction)["return_to"] == "/"
    _, backslash_transaction = authorization_request("/\\attacker.example")
    assert _decode_transaction(backslash_transaction)["return_to"] == "/"
    _, valid_transaction = authorization_request("/patient?tab=visits")
    assert _decode_transaction(valid_transaction)["return_to"] == "/patient?tab=visits"


def test_cookie_session_requires_csrf_for_state_changes():
    user_id = uuid.uuid4()
    raw_session, csrf = f"opaque-{uuid.uuid4()}", f"csrf-{uuid.uuid4()}"
    with SessionLocal() as db:
        db.add(
            ApplicationUser(
                id=user_id,
                issuer="https://issuer.test/realms/careflow",
                subject=str(user_id),
                username="patient.test",
                roles=["patient"],
                active=True,
            )
        )
        db.add(
            AuthSession(
                token_hash=hashlib.sha256(raw_session.encode()).hexdigest(),
                user_id=user_id,
                csrf_hash=hashlib.sha256(csrf.encode()).hexdigest(),
                access_token_ciphertext="unused",
                access_expires_at=datetime.now(UTC) + timedelta(minutes=5),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()

        cookie = f"careflow_session={raw_session}; careflow_csrf={csrf}"
        assert principal_from_session(db, _request("GET", cookie)).user_id == user_id
        with pytest.raises(Forbidden):
            principal_from_session(db, _request("POST", cookie))
        assert principal_from_session(db, _request("POST", cookie, csrf)).user_id == user_id


def test_hms_identity_must_match_keycloak_claim():
    principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        subject="clinician",
        roles=frozenset({"clinician"}),
        hms_username="dr.smith",
    )
    require_hms_identity(principal, "DR.SMITH")
    with pytest.raises(Forbidden):
        require_hms_identity(principal, "dr.jones")
