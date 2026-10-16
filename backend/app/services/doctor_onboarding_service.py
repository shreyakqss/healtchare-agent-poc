"""Admin > Doctors: an administrator adds a doctor to *their own* hospital, in one step.

A new doctor needs three things in two systems, and gets all of them or none:
  1. OpenEMR: the practitioner, their login, access group, specialty role and "In Office" hours
     (`openemr/provisioning.py`, one database transaction);
  2. Keycloak: a CareFlow login with the `clinician` role, `clinic_id` and `hms_username`.
Keycloak cannot join OpenEMR's transaction, so it goes second and a failure there deletes
what step 1 wrote.

Scope: the hospital is the admin's `clinic_id` login claim, never a request field, and its
YAML names the OpenEMR facility (`hospital.hms_facility_id`). An admin sees and changes only
that facility's doctors. Passwords are passed through, never stored, logged or audited.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Forbidden, NotFound, ServiceUnavailable, Unprocessable
from app.domain import provider as rules
from app.domain import scheduling
from app.integrations.hms.openemr import fhir, provisioning
from app.integrations.keycloak import admin_client
from app.models import ConsultationNote, IntakeSession, PatientCase, RoutingRecommendation, SlotHold
from app.schemas.requests import ChangeHoursRequest, NewDoctorRequest
from app.security.oidc import CurrentPrincipal
from app.services import audit, hospital_config

logger = logging.getLogger(__name__)

ROLE_LIST, SPECIALTY_LIST = "us-core-provider-role", "us-core-provider-specialty"
CLOSED_STATUSES = {"COMPLETED", "REJECTED", "FAILED"}


@dataclass(frozen=True)
class Clinic:
    id: str
    name: str
    facility_id: int
    timezone: ZoneInfo
    departments: list[dict[str, Any]]

    def today(self) -> date:
        return datetime.now(self.timezone).date()


def clinic_for(principal: CurrentPrincipal) -> Clinic:
    """The admin's own hospital, or why they cannot manage doctors."""
    if not principal.clinic_id:
        raise Forbidden("Your admin account is not linked to a hospital. Ask for `clinic_id` to be set on your login.")
    try:
        cfg = hospital_config.read(principal.clinic_id)
    except NotFound:
        raise Forbidden("Your admin account is linked to a hospital CareFlow does not know.") from None
    hospital = cfg.get("hospital") or {}
    facility_id = hospital.get("hms_facility_id")
    if not facility_id:
        raise Unprocessable(
            f"{hospital.get('name', principal.clinic_id)} is not linked to a hospital-system facility yet "
            "(set hospital.hms_facility_id in its configuration)."
        )
    return Clinic(
        id=principal.clinic_id, name=hospital.get("name") or principal.clinic_id, facility_id=int(facility_id),
        timezone=ZoneInfo(hospital.get("timezone") or "UTC"), departments=list(cfg.get("departments") or []),
    )


def _actor(principal: CurrentPrincipal) -> str:
    return f"admin:{principal.username or principal.user_id}"


# --- reads -------------------------------------------------------------------------------

def specialty_options(clinic: Clinic) -> list[dict[str, Any]]:
    """Per department, the specialties a new doctor can hold there: the department's NUCC
    codes that OpenEMR also knows, with OpenEMR's own titles."""
    titles = provisioning.list_titles(SPECIALTY_LIST)
    return [
        {
            "department_id": d["id"], "department_name": d.get("name") or d["id"],
            "specialties": [{"code": c, "title": titles[c]} for c in d.get("specialty_codes") or [] if c in titles],
        }
        for d in clinic.departments
    ]


def _weekly(clinic: Clinic, blocks: list[provisioning.Block], start: date) -> list[dict[str, Any]]:
    window = [
        (datetime.combine(d, s, clinic.timezone), datetime.combine(d, e, clinic.timezone))
        for d, s, e in blocks if start <= d < start + timedelta(days=14)
    ]
    return [h.model_dump() for h in scheduling.weekly_hours(window)]


def list_doctors(clinic: Clinic) -> list[dict[str, Any]]:
    titles = provisioning.list_titles(SPECIALTY_LIST)
    try:
        logins = {
            (u.get("attributes") or {}).get("hms_username", [""])[0].lower()
            for u in admin_client.users_by_attribute("clinic_id", clinic.id)
        }
    except ServiceUnavailable:
        logins = None  # shown as "unknown", never as "no login"
    today = clinic.today()
    out = []
    for p in provisioning.providers(clinic.facility_id):
        blocks = provisioning.office_blocks(p.id)
        future = [b for b in blocks if b[0] >= today]
        out.append({
            "id": p.id, "practitioner_id": p.uuid, "name": p.name, "username": p.username, "npi": p.npi,
            "specialty_code": p.specialty_code, "specialty": titles.get(p.specialty_code, p.specialty_code),
            "department_id": _department(clinic, p.specialty_code),
            "active": p.active,
            "has_login": None if logins is None else p.username.lower() in logins,
            "hours": _weekly(clinic, future, today),
            "hours_until": max((d for d, _, _ in future), default=None),
            # Extend repeats the last published week, so any hours ever published will do.
            "can_extend": p.active and bool(blocks),
        })
    return out


def _department(clinic: Clinic, specialty_code: str) -> str | None:
    found = fhir.match_department([specialty_code], [], clinic.departments)
    return None if found == fhir.UNKNOWN_DEPARTMENT else found


# --- checks ------------------------------------------------------------------------------

def problems(clinic: Clinic, form: NewDoctorRequest) -> list[str]:
    """Everything wrong with the form, checked against both systems. Writes nothing."""
    found: list[str] = []
    if not rules.USERNAME.fullmatch(form.username):
        found.append("Username: 3-32 characters, starting with a letter; letters, numbers, dot, dash, underscore.")
    if problem := rules.password_problem(form.password, form.username):
        found.append(problem)
    if not rules.npi_is_valid(form.npi):
        found.append("NPI must be 10 digits with a valid check digit.")
    department = next((d for d in clinic.departments if d.get("id") == form.department_id), None)
    if department is None:
        found.append("Pick one of this hospital's departments.")
    elif form.specialty_code not in (department.get("specialty_codes") or []):
        found.append("That specialty does not belong to the chosen department.")
    elif form.specialty_code not in provisioning.list_titles(SPECIALTY_LIST):
        found.append("The hospital system does not know that specialty code.")
    found += rules.hours_problems(form.days, form.ranges)
    if form.start_date < clinic.today():
        found.append("Hours cannot start in the past.")
    if not found:  # only worth asking both systems once the form itself is sound
        found += provisioning.clashes(form.username, form.npi)
        if admin_client.username_or_email_taken(form.username, form.email):
            found.append("That username or email already has a CareFlow login.")
    return found


def preview(clinic: Clinic, form: NewDoctorRequest) -> dict[str, Any]:
    blocks = rules.expand_hours(form.days, form.ranges, form.start_date, form.weeks) \
        if not rules.hours_problems(form.days, form.ranges) else []
    return {
        "problems": problems(clinic, form),
        "clinic": {"id": clinic.id, "name": clinic.name},
        "hours": _weekly(clinic, blocks, form.start_date),
        "blocks": len(blocks),
        "hours_until": max((d for d, _, _ in blocks), default=None),
    }


# --- writes ------------------------------------------------------------------------------

def create(db: Session, principal: CurrentPrincipal, form: NewDoctorRequest) -> dict[str, Any]:
    clinic = clinic_for(principal)
    if found := problems(clinic, form):
        raise Unprocessable(" ".join(found))
    blocks = rules.expand_hours(form.days, form.ranges, form.start_date, form.weeks)
    spec = provisioning.ProviderSpec(
        username=form.username, password=form.password, title=form.title, first_name=form.first_name,
        last_name=form.last_name, email=form.email, phone=form.phone, npi=form.npi,
        specialty_code=form.specialty_code,
        role_code=rules.role_code_for(form.specialty_code, set(provisioning.list_titles(ROLE_LIST))),
        licence=form.licence, facility_id=clinic.facility_id,
    )
    created = provisioning.create_provider(spec, blocks)
    try:
        login_id = admin_client.create_clinician(
            form.username, form.password, form.first_name, form.last_name, form.email,
            clinic_id=clinic.id, hms_username=form.username,
        )
    except Exception:
        logger.warning("Doctor login creation failed; removing the OpenEMR practitioner again")
        provisioning.delete_provider(created.id)
        audit.record_admin(db, clinic.id, _actor(principal), "doctor.create_failed",
                           {"username": form.username, "failed_step": "login"})
        db.commit()
        raise
    audit.record_admin(db, clinic.id, _actor(principal), "doctor.created", {
        "practitioner_id": created.uuid, "openemr_user_id": created.id, "username": form.username,
        "npi": form.npi, "department_id": form.department_id, "specialty_code": form.specialty_code,
        "keycloak_user_id": login_id, "hours_blocks": len(blocks), "hours_until": str(blocks[-1][0]),
    })
    db.commit()
    return next(d for d in list_doctors(clinic) if d["id"] == created.id)


def extend_hours(db: Session, principal: CurrentPrincipal, provider_id: int, weeks: int) -> dict[str, Any]:
    """Publish the doctor's last week of hours `weeks` more times."""
    clinic = clinic_for(principal)
    doctor = provisioning.provider(clinic.facility_id, provider_id)
    if doctor is None:
        raise NotFound("No such doctor at your hospital.")  # also another hospital's doctor
    if not doctor.active:
        raise Conflict("Reactivate this doctor before publishing hours.")
    existing = provisioning.office_blocks(provider_id)
    if not existing:
        raise Unprocessable("This doctor has no published hours to continue.")
    new = rules.repeat_last_week(existing, weeks)
    today = clinic.today()
    if new and new[-1][0] < today:  # hours lapsed long ago: restart the pattern from this week
        shift = timedelta(weeks=(today - new[0][0]).days // 7 + 1)
        new = [(d + shift, s, e) for d, s, e in new]
    new = [b for b in new if b[0] >= today]
    provisioning.add_office_blocks(provider_id, clinic.facility_id, new)
    audit.record_admin(db, clinic.id, _actor(principal), "doctor.hours_extended", {
        "openemr_user_id": provider_id, "weeks": weeks, "hours_until": str(max(d for d, _, _ in new)),
    })
    db.commit()
    return next(d for d in list_doctors(clinic) if d["id"] == provider_id)


def _held_outside(db: Session, clinic: Clinic, practitioner_id: str, from_day: date,
                  blocks: list[provisioning.Block]) -> list[datetime]:
    """Times patients already hold with this doctor, on or after `from_day`, that the new hours
    no longer cover. Those holds stay (CareFlow never moves a patient's time by itself)."""
    covered = [
        (datetime.combine(d, s, clinic.timezone), datetime.combine(d, e, clinic.timezone)) for d, s, e in blocks
    ]
    out = []
    for (start,) in db.query(SlotHold.slot_start).filter(SlotHold.practitioner_id == practitioner_id):
        local = start.astimezone(clinic.timezone)
        if local.date() < from_day:
            continue
        end = local + timedelta(minutes=scheduling.INTERVAL_MINUTES)
        if not any(s <= local and end <= e for s, e in covered):
            out.append(local)
    return sorted(out)


def _hours_change(db: Session, clinic: Clinic, provider_id: int, form: ChangeHoursRequest):
    doctor = _own_doctor(clinic, provider_id)
    found = rules.hours_problems(form.days, form.ranges)
    if form.start_date < clinic.today():
        found.append("New hours cannot start in the past.")
    if not doctor.active:
        found.append("Reactivate this doctor before changing their hours.")
    blocks = [] if found else rules.expand_hours(form.days, form.ranges, form.start_date, form.weeks)
    stranded = _held_outside(db, clinic, doctor.uuid, form.start_date, blocks) if blocks else []
    return doctor, blocks, found, stranded


def preview_hours(db: Session, principal: CurrentPrincipal, provider_id: int, form: ChangeHoursRequest) -> dict[str, Any]:
    """The new hours as patients will see them, and whose held times they would leave out. Writes nothing."""
    clinic = clinic_for(principal)
    _, blocks, found, stranded = _hours_change(db, clinic, provider_id, form)
    return {
        "problems": found,
        "hours": _weekly(clinic, blocks, form.start_date),
        "hours_until": max((d for d, _, _ in blocks), default=None),
        "held_outside": [t.isoformat() for t in stranded],
    }


def change_hours(db: Session, principal: CurrentPrincipal, provider_id: int, form: ChangeHoursRequest) -> dict[str, Any]:
    """Replace the doctor's published hours from `start_date` on. Earlier days, booked
    appointments and times patients already hold are kept."""
    clinic = clinic_for(principal)
    doctor, blocks, found, stranded = _hours_change(db, clinic, provider_id, form)
    if found:
        raise Unprocessable(" ".join(found))
    provisioning.replace_office_blocks(doctor.id, clinic.facility_id, form.start_date, blocks)
    audit.record_admin(db, clinic.id, _actor(principal), "doctor.hours_changed", {
        "openemr_user_id": doctor.id, "days": form.days, "ranges": [list(r) for r in form.ranges],
        "from": str(form.start_date), "hours_until": str(blocks[-1][0]), "held_outside": len(stranded),
    })
    db.commit()
    return next(d for d in list_doctors(clinic) if d["id"] == provider_id)


# --- removal -----------------------------------------------------------------------------
# A doctor nobody has used yet (added by mistake) is erased from both systems. One with any
# history - OpenEMR visits/notes/appointments, or CareFlow cases routed to them - is only
# deactivated, so past records keep their author: OpenEMR marks them inactive (CareFlow then
# never routes to them or accepts their sign-off), their hours stay but go unused, and the
# Keycloak login is disabled, not deleted. Open cases block either, so no patient is left
# holding a time with a doctor who is gone.

def _own_doctor(clinic: Clinic, provider_id: int) -> provisioning.Provider:
    doctor = provisioning.provider(clinic.facility_id, provider_id)
    if doctor is None:
        raise NotFound("No such doctor at your hospital.")  # also another hospital's doctor
    return doctor


def _careflow_usage(db: Session, practitioner_id: str) -> dict[str, int]:
    routed = [
        case_id for (case_id,) in
        db.query(RoutingRecommendation.case_id).filter(RoutingRecommendation.doctor_id == practitioner_id).distinct()
    ]
    open_cases = 0
    for case_id in routed:
        latest = (db.query(RoutingRecommendation.doctor_id).filter(RoutingRecommendation.case_id == case_id)
                  .order_by(RoutingRecommendation.created_at.desc()).first())
        status = (db.query(IntakeSession.status).join(PatientCase, PatientCase.session_id == IntakeSession.id)
                  .filter(PatientCase.id == case_id).scalar())
        if latest and latest[0] == practitioner_id and status not in CLOSED_STATUSES:
            open_cases += 1
    notes = db.query(ConsultationNote.id).filter(ConsultationNote.doctor_id == practitioner_id).count()
    return {"cases": len(routed), "open_cases": open_cases, "notes": notes}


def removal_check(db: Session, principal: CurrentPrincipal, provider_id: int) -> dict[str, Any]:
    """What "Remove" would do to this doctor, and anything stopping it. Changes nothing."""
    clinic = clinic_for(principal)
    doctor = _own_doctor(clinic, provider_id)
    hms = provisioning.usage(doctor.id, doctor.username)
    careflow = _careflow_usage(db, doctor.uuid)
    department = _department(clinic, doctor.specialty_code)
    colleagues = [
        p for p in provisioning.providers(clinic.facility_id)
        if p.id != doctor.id and p.active and _department(clinic, p.specialty_code) == department
    ]
    used = any(hms.values()) or careflow["cases"] or careflow["notes"]
    return {
        "doctor": {"id": doctor.id, "name": doctor.name, "username": doctor.username, "active": doctor.active},
        "mode": "deactivate" if used else "delete",
        "blocked_by_open_cases": careflow["open_cases"],
        "last_in_department": bool(department) and doctor.active and not colleagues,
        "history": {**hms, "cases": careflow["cases"], "notes": careflow["notes"]},
    }


def remove(db: Session, principal: CurrentPrincipal, provider_id: int) -> dict[str, Any]:
    clinic = clinic_for(principal)
    check = removal_check(db, principal, provider_id)
    if check["blocked_by_open_cases"]:
        n = check["blocked_by_open_cases"]
        raise Conflict(f"{check['doctor']['name']} still has {n} open case{'s' if n != 1 else ''}. "
                       "Finish or reject them first.")
    doctor = check["doctor"]
    if check["mode"] == "delete":
        admin_client.delete_username(doctor["username"])
        provisioning.delete_provider(doctor["id"])
    else:
        provisioning.set_active(doctor["id"], False)
        admin_client.set_enabled(doctor["username"], False)
    action = "doctor.deleted" if check["mode"] == "delete" else "doctor.deactivated"
    audit.record_admin(db, clinic.id, _actor(principal), action, {
        "openemr_user_id": doctor["id"], "username": doctor["username"], "history": check["history"],
    })
    db.commit()
    return {"result": "deleted" if check["mode"] == "delete" else "deactivated",
            "doctor": None if check["mode"] == "delete" else next(d for d in list_doctors(clinic) if d["id"] == doctor["id"])}


def reactivate(db: Session, principal: CurrentPrincipal, provider_id: int) -> dict[str, Any]:
    """Undo a deactivation: the login works again and the kept hours are bookable again."""
    clinic = clinic_for(principal)
    doctor = _own_doctor(clinic, provider_id)
    if doctor.active:
        raise Conflict(f"{doctor.name} is already active.")
    provisioning.set_active(doctor.id, True)
    admin_client.set_enabled(doctor.username, True)
    audit.record_admin(db, clinic.id, _actor(principal), "doctor.reactivated",
                       {"openemr_user_id": doctor.id, "username": doctor.username})
    db.commit()
    return next(d for d in list_doctors(clinic) if d["id"] == doctor.id)
