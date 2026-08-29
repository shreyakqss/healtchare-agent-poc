from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from fastapi import Depends
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound
from app.models import CaseOwner, PatientCase
from app.security.oidc import CurrentPrincipal, authenticate
from app.services import hospital_config
from app.services.pagination import CasePage, decode_case_cursor, encode_case_cursor

logger = logging.getLogger(__name__)


def require_roles(*allowed: str) -> Callable[..., CurrentPrincipal]:
    allowed_roles = frozenset(allowed)

    def dependency(principal: CurrentPrincipal = Depends(authenticate)) -> CurrentPrincipal:
        if principal.roles.isdisjoint(allowed_roles):
            logger.info("Authorization denied (role)")
            raise Forbidden("This account does not have access to this area.")
        return principal

    return dependency


def require_active_clinic(principal: CurrentPrincipal) -> None:
    if principal.clinic_id != hospital_config.active_id():
        logger.info("Authorization denied (clinic)")
        raise Forbidden("This account is not assigned to the active clinic.")


def require_hms_identity(principal: CurrentPrincipal, supplied_username: str) -> None:
    if not principal.hms_username or principal.hms_username.casefold() != supplied_username.casefold():
        logger.info("Authorization denied (HMS identity)")
        raise Forbidden("Use the hospital-system account assigned to your CareFlow login.")


def case_for_principal(
    db: Session,
    case_id: uuid.UUID,
    principal: CurrentPrincipal,
    *,
    allow_patient: bool = True,
    allow_clinician: bool = True,
) -> PatientCase:
    case = db.get(PatientCase, case_id)
    if case is None:
        raise NotFound("Patient case not found.")
    if allow_patient and "patient" in principal.roles:
        owns_case = (
            db.query(CaseOwner.id)
            .filter(CaseOwner.case_id == case.id, CaseOwner.user_id == principal.user_id)
            .first()
        )
        if owns_case:
            return case
    if allow_clinician and "clinician" in principal.roles and principal.clinic_id == case.hospital_id:
        return case
    logger.info("Authorization denied (case)")
    raise NotFound("Patient case not found.")


def cases_for_principal(
    db: Session,
    principal: CurrentPrincipal,
    as_role: str,
    *,
    limit: int,
    cursor: str | None = None,
) -> CasePage:
    query = db.query(PatientCase)
    if as_role == "clinician" and "clinician" in principal.roles:
        if not principal.clinic_id:
            raise Forbidden("A clinic assignment is required for clinical access.")
        query = query.filter(PatientCase.hospital_id == principal.clinic_id)
    elif as_role == "patient" and "patient" in principal.roles:
        query = query.join(CaseOwner, CaseOwner.case_id == PatientCase.id).filter(
            CaseOwner.user_id == principal.user_id
        )
    else:
        raise Forbidden("This account cannot access patient cases.")
    if cursor:
        created_at, case_id = decode_case_cursor(cursor)
        query = query.filter(
            or_(
                PatientCase.created_at < created_at,
                and_(PatientCase.created_at == created_at, PatientCase.id < case_id),
            )
        )
    rows = query.order_by(PatientCase.created_at.desc(), PatientCase.id.desc()).limit(limit + 1).all()
    items = rows[:limit]
    return CasePage(
        items=items,
        next_cursor=encode_case_cursor(items[-1]) if len(rows) > limit and items else None,
    )
