from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import Unauthorized
from app.db import get_db
from app.security import CurrentPrincipal, authenticate, rate_limits, require_roles
from app.security.sessions import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    TRANSACTION_COOKIE,
    authorization_request,
    complete_login,
    keycloak_logout_url,
    revoke_session,
    revoke_user_sessions,
    self_register_patient,
)

router = APIRouter(prefix="/auth", tags=["auth"])
AdminPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("admin"))]


def _cookie_options(http_only: bool = True) -> dict:
    return {
        "httponly": http_only,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }


@router.get("/login")
def login(request: Request, return_to: str | None = Query(None, max_length=512)):
    rate_limits.enforce("auth.login", rate_limits.client_identity(request))
    location, transaction = authorization_request(return_to)
    response = RedirectResponse(location, status_code=302)
    response.set_cookie(TRANSACTION_COOKIE, transaction, max_age=600, **_cookie_options())
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = Query(None, max_length=4096),
    state: str | None = Query(None, max_length=512),
    error: str | None = Query(None, max_length=128),
    db: Session = Depends(get_db),
):
    rate_limits.enforce("auth.callback", rate_limits.client_identity(request))
    transaction = request.cookies.get(TRANSACTION_COOKIE)
    if error or not code or not state or not transaction:
        raise Unauthorized("Keycloak did not complete the login.")
    session = complete_login(db, code, state, transaction)
    response = RedirectResponse(session.return_to, status_code=303)
    response.delete_cookie(TRANSACTION_COOKIE, **_cookie_options())
    response.set_cookie(
        SESSION_COOKIE,
        session.session_token,
        max_age=settings.AUTH_SESSION_HOURS * 3600,
        **_cookie_options(),
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=settings.AUTH_SESSION_HOURS * 3600,
        **_cookie_options(http_only=False),
    )
    return response


@router.post("/self-register")
def self_register(
    request: Request,
    response: Response,
    return_to: str | None = Query(None, max_length=512),
    db: Session = Depends(get_db),
):
    rate_limits.enforce("auth.self_register", rate_limits.client_identity(request))
    session, username, password = self_register_patient(db, return_to)
    response.set_cookie(
        SESSION_COOKIE, session.session_token, max_age=settings.AUTH_SESSION_HOURS * 3600, **_cookie_options(),
    )
    response.set_cookie(
        CSRF_COOKIE, session.csrf_token, max_age=settings.AUTH_SESSION_HOURS * 3600, **_cookie_options(http_only=False),
    )
    return {"username": username, "password": password, "return_to": session.return_to}


@router.get("/me")
def current_user(principal: CurrentPrincipal = Depends(authenticate)):
    return {
        "user_id": str(principal.user_id),
        "subject": principal.subject,
        "username": principal.username,
        "email": principal.email,
        "display_name": principal.display_name,
        "roles": sorted(principal.roles),
        "clinic_id": principal.clinic_id,
        "hms_username": principal.hms_username,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    id_token = revoke_session(db, request)
    response.delete_cookie(SESSION_COOKIE, **_cookie_options())
    response.delete_cookie(CSRF_COOKIE, **_cookie_options(http_only=False))
    return {"logout_url": keycloak_logout_url(id_token)}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: uuid.UUID, _: AdminPrincipal, db: Session = Depends(get_db)):
    return {"revoked": revoke_user_sessions(db, user_id)}
