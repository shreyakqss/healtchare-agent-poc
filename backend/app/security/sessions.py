from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Forbidden, ServiceUnavailable, Unauthorized
from app.models import ApplicationUser, AuthSession

logger = logging.getLogger(__name__)

APP_ROLES = frozenset({"patient", "clinician", "admin"})
SESSION_COOKIE = "careflow_session"
CSRF_COOKIE = "careflow_csrf"
TRANSACTION_COOKIE = "careflow_oidc_transaction"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class LoginSession:
    session_token: str
    csrf_token: str
    return_to: str


def _now() -> datetime:
    return datetime.now(UTC)


def _keyring() -> dict[str, bytes]:
    if settings.AUTH_SESSION_KEYS:
        return {key_id: value.encode() for key_id, value in settings.AUTH_SESSION_KEYS.items()}
    value = settings.AUTH_SESSION_SECRET
    if value is None or len(value.encode()) < 32:
        raise ServiceUnavailable("No valid CareFlow session encryption key is configured.")
    return {"legacy": value.encode()}


def _active_key() -> tuple[str, bytes]:
    keys = _keyring()
    key_id = settings.AUTH_ACTIVE_KEY_ID if settings.AUTH_SESSION_KEYS else "legacy"
    try:
        return key_id, keys[key_id]
    except KeyError as exc:
        raise ServiceUnavailable("The active CareFlow session key is unavailable.") from exc


def _fernet(secret: bytes) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _encrypt(value: str | None) -> str | None:
    if not value:
        return None
    key_id, secret = _active_key()
    return f"{key_id}${_fernet(secret).encrypt(value.encode()).decode()}"


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    keys = _keyring()
    candidates: list[tuple[str, bytes]]
    if "$" in value:
        key_id, value = value.split("$", 1)
        candidates = [(key_id, keys[key_id])] if key_id in keys else []
    else:
        candidates = list(keys.items())
    for _, secret in candidates:
        try:
            return _fernet(secret).decrypt(value.encode()).decode()
        except InvalidToken:
            continue
    raise Unauthorized("The CareFlow session is invalid.")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _encode_transaction(payload: dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode()
    key_id, secret = _active_key()
    signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{key_id}.{encoded}.{signature}"


def _decode_transaction(value: str) -> dict[str, Any]:
    try:
        parts = value.split(".", 2)
        if len(parts) == 3:
            key_id, encoded, signature = parts
            secret = _keyring()[key_id]
        else:
            encoded, signature = value.rsplit(".", 1)
            secret = _keyring()["legacy"]
        expected = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
        if not isinstance(payload, dict):
            raise ValueError
        age = _now().timestamp() - float(payload["iat"])
        if age < -30 or age > 600:
            raise ValueError
        return payload
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise Unauthorized("The login transaction is invalid or expired.") from exc


def _safe_return_to(value: str | None) -> str:
    candidate = value or "/"
    parsed = urlsplit(candidate)
    safe = (
        candidate.startswith("/")
        and not candidate.startswith("//")
        and "\\" not in candidate
        and not parsed.scheme
        and not parsed.netloc
        and all(ord(char) >= 32 for char in candidate)
    )
    return candidate if safe else "/"


def application_roles(claims: dict[str, Any]) -> frozenset[str]:
    realm_access = claims.get("realm_access")
    raw_roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    return frozenset(role for role in raw_roles if isinstance(role, str) and role in APP_ROLES)


def authorization_request(return_to: str | None) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    transaction = _encode_transaction(
        {"state": state, "nonce": nonce, "verifier": verifier, "return_to": _safe_return_to(return_to), "iat": _now().timestamp()}
    )
    query = urlencode(
        {
            "client_id": settings.OIDC_WEB_CLIENT_ID,
            "redirect_uri": settings.OIDC_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{settings.OIDC_ISSUER_URL.rstrip('/')}/protocol/openid-connect/auth?{query}", transaction


def _token_request(data: dict[str, str]) -> dict[str, Any]:
    response = httpx.post(
        f"{settings.OIDC_ISSUER_URL.rstrip('/')}/protocol/openid-connect/token",
        data=data,
        headers={"Accept": "application/json"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("OIDC token response is not an object")
    return payload


def _sync_user(db: Session, claims: dict[str, Any]) -> ApplicationUser:
    issuer, subject = claims["iss"], claims["sub"]
    roles = application_roles(claims)
    if not roles:
        raise Forbidden("This account has no CareFlow role.")
    user = (
        db.query(ApplicationUser)
        .filter(ApplicationUser.issuer == issuer, ApplicationUser.subject == subject)
        .first()
    )
    if user is None:
        user = ApplicationUser(issuer=issuer, subject=subject, active=True)
        db.add(user)
    elif not user.active:
        raise Forbidden("This CareFlow account is disabled.")
    user.username = claims.get("preferred_username") if isinstance(claims.get("preferred_username"), str) else None
    user.email = claims.get("email") if isinstance(claims.get("email"), str) else None
    user.display_name = claims.get("name") if isinstance(claims.get("name"), str) else None
    user.roles = sorted(roles)
    user.clinic_id = claims.get("clinic_id") if isinstance(claims.get("clinic_id"), str) else None
    user.hms_username = claims.get("hms_username") if isinstance(claims.get("hms_username"), str) else None
    user.hms_patient_id = claims.get("hms_patient_id") if isinstance(claims.get("hms_patient_id"), str) else None
    user.last_login_at = _now()
    db.flush()
    return user


def _finish_login(db: Session, tokens: dict[str, Any], access_claims: dict[str, Any], return_to: str) -> LoginSession:
    """Shared tail of every login path (authorization-code callback, self-registration):
    sync the CareFlow user row and mint a CareFlow session from already-verified tokens."""
    access_token = tokens["access_token"]
    id_token = tokens.get("id_token")
    user = _sync_user(db, access_claims)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    access_expiry = datetime.fromtimestamp(int(access_claims["exp"]), UTC)
    absolute_expiry = _now() + timedelta(hours=settings.AUTH_SESSION_HOURS)
    refresh_expires = tokens.get("refresh_expires_in")
    if isinstance(refresh_expires, int) and refresh_expires > 0:
        absolute_expiry = min(absolute_expiry, _now() + timedelta(seconds=refresh_expires))
    db.add(
        AuthSession(
            token_hash=_hash(session_token),
            user_id=user.id,
            csrf_hash=_hash(csrf_token),
            encryption_key_id=_active_key()[0],
            access_token_ciphertext=_encrypt(access_token),
            refresh_token_ciphertext=_encrypt(
                tokens.get("refresh_token") if isinstance(tokens.get("refresh_token"), str) else None
            ),
            id_token_ciphertext=_encrypt(id_token if isinstance(id_token, str) else None),
            access_expires_at=access_expiry,
            expires_at=absolute_expiry,
        )
    )
    db.commit()
    logger.info("Authentication succeeded")
    return LoginSession(session_token=session_token, csrf_token=csrf_token, return_to=_safe_return_to(return_to))


def complete_login(db: Session, code: str, state: str, transaction_cookie: str) -> LoginSession:
    transaction = _decode_transaction(transaction_cookie)
    if not hmac.compare_digest(state, str(transaction.get("state", ""))):
        raise Unauthorized("The login state did not match.")
    try:
        tokens = _token_request(
            {
                "grant_type": "authorization_code",
                "client_id": settings.OIDC_WEB_CLIENT_ID,
                "redirect_uri": settings.OIDC_REDIRECT_URI,
                "code": code,
                "code_verifier": str(transaction["verifier"]),
            }
        )
        access_token = tokens["access_token"]
        id_token = tokens["id_token"]
        if not isinstance(access_token, str) or not isinstance(id_token, str):
            raise ValueError("missing tokens")
        from app.security.oidc import OidcVerifier, configured_verifier

        access_claims = configured_verifier().claims(access_token)
        id_claims = OidcVerifier(
            settings.OIDC_ISSUER_URL,
            settings.OIDC_WEB_CLIENT_ID,
            settings.OIDC_JWKS_TTL_SECONDS,
        ).claims(id_token, nonce=str(transaction["nonce"]))
        if access_claims is None or id_claims is None or access_claims["sub"] != id_claims["sub"]:
            raise ValueError("token validation failed")
    except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        logger.warning("OIDC login exchange failed (%s)", type(exc).__name__)
        raise Unauthorized("Keycloak could not complete the login.") from exc

    return _finish_login(db, tokens, access_claims, str(transaction.get("return_to")))


def self_register_patient(db: Session, return_to: str | None) -> tuple[LoginSession, str, str]:
    """New-patient self-signup from the landing page: creates a fresh Keycloak account
    (role patient) with a generated username/password, logs it straight into a CareFlow
    session (no Keycloak login screen), and returns the credentials once so the patient
    can save them for a returning visit. The intake form itself creates the OpenEMR record
    on first submit - nothing OpenEMR-side happens here."""
    from app.integrations.keycloak import admin_client
    from app.security.oidc import OidcVerifier, configured_verifier

    username = f"patient-{secrets.token_hex(4)}"
    password = username
    admin_client.create_user(username, password, "patient")
    try:
        tokens = _token_request(
            {
                "grant_type": "password",
                "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
                "username": username,
                "password": password,
                "scope": "openid",
            }
        )
        access_token = tokens["access_token"]
        id_token = tokens["id_token"]
        if not isinstance(access_token, str) or not isinstance(id_token, str):
            raise ValueError("missing tokens")
        access_claims = configured_verifier().claims(access_token)
        id_claims = OidcVerifier(
            settings.OIDC_ISSUER_URL, str(settings.KEYCLOAK_ADMIN_CLIENT_ID), settings.OIDC_JWKS_TTL_SECONDS
        ).claims(id_token)
        if access_claims is None or id_claims is None or access_claims["sub"] != id_claims["sub"]:
            raise ValueError("token validation failed")
    except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        logger.warning("Self-registration login failed (%s)", type(exc).__name__)
        raise Unauthorized("Could not sign in the new account.") from exc

    session = _finish_login(db, tokens, access_claims, return_to or "/patient")
    return session, username, password


def _rewrap_session(db: Session, row: AuthSession) -> AuthSession:
    active_key_id = _active_key()[0]
    if row.encryption_key_id == active_key_id:
        return row
    row = db.query(AuthSession).filter(AuthSession.id == row.id).with_for_update().one()
    if row.encryption_key_id != active_key_id:
        access_token = _decrypt(row.access_token_ciphertext)
        refresh_token = _decrypt(row.refresh_token_ciphertext)
        id_token = _decrypt(row.id_token_ciphertext)
        row.access_token_ciphertext = _encrypt(access_token)
        row.refresh_token_ciphertext = _encrypt(refresh_token)
        row.id_token_ciphertext = _encrypt(id_token)
        row.encryption_key_id = active_key_id
        db.commit()
    return row


def _refresh(db: Session, row: AuthSession) -> ApplicationUser:
    row = db.query(AuthSession).filter(AuthSession.id == row.id).with_for_update().one()
    now = _now()
    user = db.get(ApplicationUser, row.user_id)
    if row.revoked_at is not None or row.expires_at <= now or user is None:
        raise Unauthorized("The CareFlow session expired. Sign in again.")
    if row.access_expires_at > now + timedelta(seconds=30):
        return user
    refresh_token = _decrypt(row.refresh_token_ciphertext)
    if refresh_token is None:
        row.revoked_at = _now()
        db.commit()
        raise Unauthorized("The CareFlow session expired. Sign in again.")
    try:
        tokens = _token_request(
            {
                "grant_type": "refresh_token",
                "client_id": settings.OIDC_WEB_CLIENT_ID,
                "refresh_token": refresh_token,
            }
        )
        access_token = tokens["access_token"]
        if not isinstance(access_token, str):
            raise ValueError("missing access token")
        from app.security.oidc import configured_verifier

        claims = configured_verifier().claims(access_token)
        if claims is None or user is None or claims["sub"] != user.subject or claims["iss"] != user.issuer:
            raise ValueError("token validation failed")
        if not user.active:
            raise Unauthorized("This CareFlow account is disabled.")
        user = _sync_user(db, claims)
        row.access_token_ciphertext = _encrypt(access_token)
        row.access_expires_at = datetime.fromtimestamp(int(claims["exp"]), UTC)
        if isinstance(tokens.get("refresh_token"), str):
            row.refresh_token_ciphertext = _encrypt(tokens["refresh_token"])
        if isinstance(tokens.get("id_token"), str):
            row.id_token_ciphertext = _encrypt(tokens["id_token"])
        db.commit()
        return user
    except Unauthorized:
        row.revoked_at = _now()
        db.commit()
        raise
    except (KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        row.revoked_at = _now()
        db.commit()
        logger.warning("OIDC session refresh failed (%s)", type(exc).__name__)
        raise Unauthorized("The CareFlow session expired. Sign in again.") from exc


def principal_from_session(db: Session, request: Request):
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not raw_session:
        return None
    row = db.query(AuthSession).filter(AuthSession.token_hash == _hash(raw_session)).first()
    now = _now()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    if request.method.upper() in UNSAFE_METHODS:
        csrf_cookie = request.cookies.get(CSRF_COOKIE)
        csrf_header = request.headers.get("x-csrf-token")
        if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
            raise Forbidden("The CSRF token is missing or invalid.")
        if not hmac.compare_digest(row.csrf_hash, _hash(csrf_header)):
            raise Forbidden("The CSRF token is missing or invalid.")
    user = db.get(ApplicationUser, row.user_id)
    if user is None or not user.active:
        return None
    row = _rewrap_session(db, row)
    if row.access_expires_at <= now + timedelta(seconds=30):
        user = _refresh(db, row)
    from app.security.oidc import CurrentPrincipal

    return CurrentPrincipal(
        user_id=user.id,
        subject=user.subject,
        roles=frozenset(role for role in user.roles if role in APP_ROLES),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        clinic_id=user.clinic_id,
        hms_username=user.hms_username,
        hms_patient_id=user.hms_patient_id,
        auth_method="session",
    )


def revoke_session(db: Session, request: Request) -> str | None:
    raw_session = request.cookies.get(SESSION_COOKIE)
    if not raw_session:
        return None
    row = db.query(AuthSession).filter(AuthSession.token_hash == _hash(raw_session)).first()
    if row is None:
        return None
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise Forbidden("The CSRF token is missing or invalid.")
    if not hmac.compare_digest(row.csrf_hash, _hash(csrf_header)):
        raise Forbidden("The CSRF token is missing or invalid.")
    id_token = _decrypt(row.id_token_ciphertext)
    row.revoked_at = _now()
    db.commit()
    return id_token


def revoke_user_sessions(db: Session, user_id) -> int:
    revoked = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .update({AuthSession.revoked_at: _now()}, synchronize_session=False)
    )
    db.commit()
    logger.info("Administrator revoked %s sessions", revoked)
    return revoked


def keycloak_logout_url(id_token: str | None) -> str:
    params = {
        "client_id": settings.OIDC_WEB_CLIENT_ID,
        "post_logout_redirect_uri": f"{settings.FRONTEND_URL.rstrip('/')}/",
    }
    if id_token:
        params["id_token_hint"] = id_token
    return f"{settings.OIDC_ISSUER_URL.rstrip('/')}/protocol/openid-connect/logout?{urlencode(params)}"
