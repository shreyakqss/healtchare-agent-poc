"""OIDC access-token verification for the Keycloak integration boundary."""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ServiceUnavailable, Unauthorized
from app.db import get_db
from app.models import ApplicationUser

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: uuid.UUID
    subject: str
    roles: frozenset[str]
    username: str | None = None
    clinic_id: str | None = None
    hms_username: str | None = None
    auth_method: str = "bearer"


class OidcVerifier:
    def __init__(self, issuer: str, audience: str, ttl_seconds: int = 300):
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_url = f"{self._issuer}/protocol/openid-connect/certs"
        self._ttl_seconds = ttl_seconds
        self._keys: list[dict[str, Any]] | None = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def _fetch_jwks(self, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh and self._keys is not None and time.monotonic() < self._expiry:
            return self._keys
        with self._lock:
            if not refresh and self._keys is not None and time.monotonic() < self._expiry:
                return self._keys
            response = httpx.get(self._jwks_url, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            self._keys = payload.get("keys") if isinstance(payload, dict) else []
            if not isinstance(self._keys, list):
                self._keys = []
            self._expiry = time.monotonic() + self._ttl_seconds
            return self._keys

    def _key(self, header: dict[str, Any]) -> Any | None:
        kid = header.get("kid")
        for attempt in range(2):
            keys = self._fetch_jwks(refresh=attempt == 1)
            match = next((key for key in keys if key.get("kid") == kid), None)
            if match:
                return RSAAlgorithm.from_jwk(json.dumps(match))
        return None

    def claims(self, token: str, nonce: str | None = None) -> dict[str, Any] | None:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                return None
            key = self._key(header)
            if key is None:
                return None
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
            if not isinstance(claims.get("sub"), str) or not claims["sub"]:
                return None
            if nonce is not None and claims.get("nonce") != nonce:
                return None
            return claims
        except Exception:  # A rejected token must not expose token or claim contents.
            return None


_verifier: OidcVerifier | None = None
_verifier_lock = threading.Lock()


def configured_verifier() -> OidcVerifier:
    global _verifier
    if _verifier is None:
        with _verifier_lock:
            if _verifier is None:
                _verifier = OidcVerifier(
                    settings.OIDC_ISSUER_URL,
                    settings.OIDC_AUDIENCE,
                    settings.OIDC_JWKS_TTL_SECONDS,
                )
    return _verifier


def _claims_principal(db: Session, claims: dict[str, Any], auth_method: str) -> CurrentPrincipal:
    from app.security.sessions import application_roles

    issuer = claims["iss"]
    subject = claims["sub"]
    roles = application_roles(claims)
    clinic_id = claims.get("clinic_id") if isinstance(claims.get("clinic_id"), str) else None
    hms_username = claims.get("hms_username") if isinstance(claims.get("hms_username"), str) else None
    username = claims.get("preferred_username") if isinstance(claims.get("preferred_username"), str) else None
    user = (
        db.query(ApplicationUser)
        .filter(ApplicationUser.issuer == issuer, ApplicationUser.subject == subject)
        .first()
    )
    if user is None:
        user = ApplicationUser(issuer=issuer, subject=subject, active=True)
        db.add(user)
    elif not user.active:
        raise Unauthorized("This CareFlow account is disabled.")
    changed = (user.username, user.roles, user.clinic_id, user.hms_username) != (
        username,
        sorted(roles),
        clinic_id,
        hms_username,
    )
    if changed or user.id is None:
        user.username = username
        user.roles = sorted(roles)
        user.clinic_id = clinic_id
        user.hms_username = hms_username
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return CurrentPrincipal(
        user_id=user.id,
        subject=subject,
        roles=roles,
        username=username,
        clinic_id=clinic_id,
        hms_username=hms_username,
        auth_method=auth_method,
    )


def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentPrincipal:
    if settings.AUTH_MODE != "oidc":
        raise ServiceUnavailable("OIDC authentication is not enabled for this deployment.")
    if credentials is not None and credentials.scheme.lower() == "bearer":
        claims = configured_verifier().claims(credentials.credentials)
        if claims is None:
            raise Unauthorized("The access token is invalid or expired.")
        return _claims_principal(db, claims, "bearer")

    from app.security.sessions import principal_from_session

    principal = principal_from_session(db, request)
    if principal is None:
        raise Unauthorized("Sign in is required.")
    return principal
