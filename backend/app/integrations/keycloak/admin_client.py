"""Keycloak Admin REST API - the one place CareFlow's backend acts as an operator rather
than a signed-in user: creating a Keycloak account for self-registered patients. Uses the
`careflow-admin` service-account client, which holds only manage-users/view-users.
Also creates doctors' logins for Admin > Doctors (services/doctor_onboarding_service.py)."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.errors import Conflict, ServiceUnavailable


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


def _admin() -> tuple[str, dict[str, str]]:
    base = f"{settings.KEYCLOAK_ADMIN_URL.rstrip('/')}/admin/realms/{settings.KEYCLOAK_REALM}"
    return base, {"Authorization": f"Bearer {_admin_token()}", "Content-Type": "application/json"}


def username_or_email_taken(username: str, email: str) -> bool:
    try:
        base, headers = _admin()
        by_name = httpx.get(f"{base}/users", params={"username": username, "exact": "true"}, headers=headers, timeout=10.0)
        by_email = httpx.get(f"{base}/users", params={"email": email, "exact": "true"}, headers=headers, timeout=10.0)
        by_name.raise_for_status()
        by_email.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system is unreachable.") from exc
    return bool(by_name.json()) or bool(by_email.json())


def create_clinician(
    username: str, password: str, first_name: str, last_name: str, email: str, clinic_id: str, hms_username: str,
) -> str:
    """A doctor's CareFlow login: the `clinician` role plus the two attributes the token carries
    (`clinic_id` scopes them to their hospital; `hms_username` ties their sign-offs to their
    OpenEMR account). Returns the Keycloak user id. On any failure after the user exists, the
    user is deleted again so the caller never has to clean up a half-made login."""
    try:
        base, headers = _admin()
        response = httpx.post(
            f"{base}/users",
            headers=headers,
            json={
                "username": username, "enabled": True, "firstName": first_name, "lastName": last_name,
                "email": email, "emailVerified": True,
                "attributes": {"clinic_id": [clinic_id], "hms_username": [hms_username]},
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system is unreachable.") from exc
    if response.status_code == 409:
        raise Conflict("That username or email is already used in the login system.")
    if response.status_code != 201:
        raise ServiceUnavailable("The login system could not create the account.")
    user_id = response.headers["Location"].rsplit("/", 1)[-1]
    try:
        available = httpx.get(f"{base}/users/{user_id}/role-mappings/realm/available", headers=headers, timeout=10.0)
        available.raise_for_status()
        role = next((r for r in available.json() if r.get("name") == "clinician"), None)
        if role is None:
            raise ServiceUnavailable("Keycloak realm role 'clinician' is not available to assign.")
        httpx.post(f"{base}/users/{user_id}/role-mappings/realm", headers=headers, json=[role], timeout=10.0).raise_for_status()
    except (httpx.HTTPError, ServiceUnavailable) as exc:
        delete_user(user_id)
        raise ServiceUnavailable("The login system could not give the account the doctor role.") from exc
    return user_id


def delete_user(user_id: str) -> None:
    """Best-effort removal, used to undo a creation."""
    try:
        base, headers = _admin()
        httpx.delete(f"{base}/users/{user_id}", headers=headers, timeout=10.0)
    except httpx.HTTPError:
        pass


def users_by_attribute(name: str, value: str) -> list[dict]:
    """Logins carrying an attribute value, e.g. every account of one clinic."""
    try:
        base, headers = _admin()
        response = httpx.get(f"{base}/users", params={"q": f"{name}:{value}", "max": 500}, headers=headers, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system is unreachable.") from exc
    return response.json()


def _user_by_username(username: str) -> tuple[str, dict[str, str], dict | None]:
    try:
        base, headers = _admin()
        response = httpx.get(f"{base}/users", params={"username": username, "exact": "true"}, headers=headers, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system is unreachable.") from exc
    found = response.json()
    return base, headers, found[0] if found else None


def set_enabled(username: str, enabled: bool) -> bool:
    """Disable (or re-enable) a login, keeping it. False if there is no such login."""
    base, headers, user = _user_by_username(username)
    if user is None:
        return False
    try:
        httpx.put(f"{base}/users/{user['id']}", headers=headers, json={**user, "enabled": enabled}, timeout=10.0).raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system could not update the account.") from exc
    return True


def set_email(username: str, email: str) -> None:
    """Change a login's email. Conflict if another login already uses it; no login, nothing to do."""
    base, headers, user = _user_by_username(username)
    if user is None:
        return
    try:
        taken = httpx.get(f"{base}/users", params={"email": email, "exact": "true"}, headers=headers, timeout=10.0)
        taken.raise_for_status()
        if any(u["id"] != user["id"] for u in taken.json()):
            raise Conflict("That email is already used by another login.")
        response = httpx.put(f"{base}/users/{user['id']}", headers=headers,
                             json={**user, "email": email, "emailVerified": True}, timeout=10.0)
    except httpx.HTTPError as exc:
        raise ServiceUnavailable("The login system could not update the account.") from exc
    if response.status_code == 409:
        raise Conflict("That email is already used by another login.")
    if response.status_code >= 400:
        raise ServiceUnavailable("The login system could not update the account.")


def delete_username(username: str) -> None:
    _, _, user = _user_by_username(username)
    if user is not None:
        delete_user(user["id"])
