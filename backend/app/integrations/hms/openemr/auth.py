"""OAuth2 / OIDC plumbing for OpenEMR.

Two independent concerns live here:

- `TokenProvider` keeps the adapter's own service-account access token fresh. OpenEMR
  only authorises `user/*` scopes under the password grant; `client_credentials` is kept
  for installs that grant `system/*` scopes via JWKS-based client auth.
- `IdTokenVerifier` validates the `id_token` OpenEMR returns for a clinician's *own*
  login (see `FhirHMS.verify_credentials`), so a review/consultation action is attributed
  to a verified identity rather than a free-text name.

Both are used from a threadpool (blocking HTTP is offloaded with `asyncio.to_thread`), so
their caches are guarded by real locks.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
_JWKS_TTL_SECONDS = 3600
_TOKEN_REFRESH_MARGIN_SECONDS = 30
# OpenEMR-specific form field: distinguishes a staff/provider login from a patient-portal
# login. "users" is the value for a clinic user such as "admin".
_STAFF_USER_ROLE = "users"


@dataclass(frozen=True)
class OAuthConfig:
    token_url: str
    client_id: str | None
    client_secret: str | None
    scopes: str
    username: str | None = None
    password: str | None = None

    @property
    def jwks_url(self) -> str:
        # OpenEMR's OIDC discovery publishes jwks_uri at "{issuer}/jwk" (singular), sharing
        # the token URL's "{issuer}/token" base.
        return self.token_url.rsplit("/", 1)[0] + "/jwk"

    @property
    def issuer(self) -> str:
        return self.token_url.rsplit("/", 1)[0]

    def password_grant(self, username: str, password: str) -> dict[str, str]:
        return {
            "grant_type": "password",
            "client_id": self.client_id or "",
            "client_secret": self.client_secret or "",
            "username": username,
            "password": password,
            "scope": self.scopes,
            "user_role": _STAFF_USER_ROLE,
        }

    def client_credentials_grant(self) -> dict[str, str]:
        return {
            "grant_type": "client_credentials",
            "client_id": self.client_id or "",
            "client_secret": self.client_secret or "",
            "scope": self.scopes,
        }


def request_token(config: OAuthConfig, form: dict[str, str]) -> httpx.Response:
    """One POST to the token endpoint. Callers decide how to treat non-2xx."""
    return httpx.post(config.token_url, data=form, timeout=TIMEOUT_SECONDS)


class TokenProvider:
    """Cached service-account access token with early refresh and a double-checked lock."""

    def __init__(self, config: OAuthConfig):
        self._config = config
        self._token: str | None = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def _is_fresh(self) -> bool:
        return self._token is not None and time.monotonic() < self._expiry

    def _fetch(self) -> str:
        cfg = self._config
        if cfg.username and cfg.password:
            form = cfg.password_grant(cfg.username, cfg.password)
        else:
            form = cfg.client_credentials_grant()
        resp = request_token(cfg, form)
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        lifetime = int(payload.get("expires_in", 300))
        self._expiry = time.monotonic() + max(lifetime - _TOKEN_REFRESH_MARGIN_SECONDS, 1)
        return self._token

    def access_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._is_fresh():
            return self._token  # type: ignore[return-value]
        with self._lock:
            if not force_refresh and self._is_fresh():
                return self._token  # type: ignore[return-value]
            return self._fetch()


class IdTokenVerifier:
    """Verifies an OIDC id_token's RS256 signature against OpenEMR's JWKS and returns its claims."""

    def __init__(self, config: OAuthConfig):
        self._config = config
        self._keys: list[dict[str, Any]] | None = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def _is_fresh(self) -> bool:
        return self._keys is not None and time.monotonic() < self._expiry

    def _fetch_jwks(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if not force_refresh and self._is_fresh():
            return self._keys  # type: ignore[return-value]
        with self._lock:
            if not force_refresh and self._is_fresh():
                return self._keys  # type: ignore[return-value]
            resp = httpx.get(self._config.jwks_url, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            self._keys = resp.json().get("keys") or []
            self._expiry = time.monotonic() + _JWKS_TTL_SECONDS
            return self._keys

    def _signing_key(self, header: dict[str, Any]) -> Any | None:
        """Key matching the header `kid`, refreshing once on a miss (key rotation). Falls back
        to the sole published key when neither side carries a `kid` - the case on a stock
        OpenEMR install (single RSA signing key, no `kid`)."""
        kid = header.get("kid")
        for attempt in range(2):
            keys = self._fetch_jwks(force_refresh=attempt == 1)
            if kid is not None:
                for key in keys:
                    if key.get("kid") == kid:
                        return RSAAlgorithm.from_jwk(json.dumps(key))
                continue
            return RSAAlgorithm.from_jwk(json.dumps(keys[0])) if len(keys) == 1 else None
        return None

    def claims(self, id_token: str) -> dict[str, Any] | None:
        """Verified claims, or None on any failure. Logs the exception type only (never the
        token or claim contents - PHI-log-scrubbing convention)."""
        try:
            key = self._signing_key(jwt.get_unverified_header(id_token))
            if key is None:
                logger.warning("id_token verification: no matching JWKS signing key")
                return None
            return jwt.decode(
                id_token,
                key=key,
                algorithms=["RS256"],
                audience=self._config.client_id,
                issuer=self._config.issuer,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except Exception as exc:  # noqa: BLE001 - a login check must never raise
            logger.warning("id_token verification failed (%s)", type(exc).__name__)
            return None
