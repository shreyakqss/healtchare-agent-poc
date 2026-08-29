import json
import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.security import HTTPAuthorizationCredentials
from jwt.algorithms import RSAAlgorithm
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import ServiceUnavailable, Unauthorized
from app.db import SessionLocal
from app.security.oidc import OidcVerifier, authenticate

ISSUER = "http://localhost:8500/realms/careflow"
AUDIENCE = "careflow-api"


def _keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(public))
    jwk["kid"] = "test-key"
    return private, jwk


def _token(private, **overrides):
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "preferred_username": "dr.test",
        "realm_access": {"roles": ["clinician"]},
        **overrides,
    }
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"})


def test_oidc_verifier_requires_expected_issuer_and_audience():
    private, jwk = _keypair()
    verifier = OidcVerifier(ISSUER, AUDIENCE)
    with patch.object(verifier, "_fetch_jwks", return_value=[jwk]):
        assert verifier.claims(_token(private))["sub"] == "user-123"
        assert verifier.claims(_token(private, iss="https://wrong.example")) is None
        assert verifier.claims(_token(private, aud="other-api")) is None


def test_authenticate_maps_minimal_principal(monkeypatch):
    private, jwk = _keypair()
    verifier = OidcVerifier(ISSUER, AUDIENCE)
    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_token(private, clinic_id="clinic-1"))
    request = Request({"type": "http", "method": "GET", "headers": []})
    with SessionLocal() as db, patch.object(verifier, "_fetch_jwks", return_value=[jwk]):
        with patch("app.security.oidc.configured_verifier", return_value=verifier):
            principal = authenticate(request, credentials, db)
    assert principal.subject == "user-123"
    assert principal.username == "dr.test"
    assert principal.roles == {"clinician"}
    assert principal.clinic_id == "clinic-1"


def test_authenticate_fails_closed_when_oidc_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "disabled")
    with pytest.raises(ServiceUnavailable):
        authenticate(Request({"type": "http", "method": "GET", "headers": []}), None, None)


def test_authenticate_rejects_missing_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    request = Request({"type": "http", "method": "GET", "headers": []})
    with SessionLocal() as db, pytest.raises(Unauthorized):
        authenticate(request, None, db)
