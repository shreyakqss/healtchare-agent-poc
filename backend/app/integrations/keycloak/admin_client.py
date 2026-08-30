"""Keycloak Admin REST API - the one place CareFlow's backend acts as an operator rather
than a signed-in user: creating a Keycloak account for self-registered patients. Uses the
`careflow-admin` service-account client, which holds only manage-users/view-users."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import ServiceUnavailable


def _admin_token() -> str:
    response = httpx.post(
        f"{settings.KEYCLOAK_ADMIN_URL.rstrip('/')}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def create_user(username: str, password: str, role: str) -> str:
    """Creates an enabled Keycloak user with a real (non-temporary) password and one
    realm role. Returns the new user's Keycloak id (their tokens' `sub` claim)."""
    token = _admin_token()
    base = f"{settings.KEYCLOAK_ADMIN_URL.rstrip('/')}/admin/realms/{settings.KEYCLOAK_REALM}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = httpx.post(
        f"{base}/users",
        headers=headers,
        json={
            "username": username,
            "enabled": True,
            # The realm's user profile requires firstName/lastName/email - real values are
            # collected later by the intake form itself, so these are placeholders only.
            "firstName": "New",
            "lastName": "Patient",
            "email": f"{username}@self-register.careflow.local",
            "emailVerified": True,
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        },
        timeout=10.0,
    )
    if response.status_code != 201:
        raise ServiceUnavailable("Keycloak could not create the account.")
    user_id = response.headers["Location"].rsplit("/", 1)[-1]

    # GET /roles/{name} needs the broader view-realm permission; the user-scoped "available
    # roles to assign" list only needs manage-users, which this service account already has.
    available_response = httpx.get(f"{base}/users/{user_id}/role-mappings/realm/available", headers=headers, timeout=10.0)
    available_response.raise_for_status()
    role_repr = next((r for r in available_response.json() if r.get("name") == role), None)
    if role_repr is None:
        raise ServiceUnavailable(f"Keycloak realm role {role!r} is not available to assign.")
    assign_response = httpx.post(
        f"{base}/users/{user_id}/role-mappings/realm",
        headers=headers,
        json=[role_repr],
        timeout=10.0,
    )
    assign_response.raise_for_status()
    return user_id
