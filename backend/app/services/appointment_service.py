"""The patient's booking among the department's open times.

Routing assigns the doctor with the earliest free time. The patient may pick a time with any of
the department's doctors, and the case moves to that doctor - unless urgency rules out a choice
(domain/routing.NO_DOCTOR_CHOICE): then they see only the earliest time at each hour, whoever's
it is. Once a clinician has reviewed the case, the doctor is fixed and only their times are offered.

Confirming a time books it: the appointment goes straight onto the doctor's HMS calendar, with no
clinician approval (instant booking, as Zocdoc-style apps do). The clinician's review prepares
the visit; it never gates the booking. Changing the time moves the booking."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.core.errors import Conflict, ServiceUnavailable, Unprocessable
from app.domain import routing as routing_rules
from app.integrations.hms import get_hms
from app.models import PatientCase, RoutingRecommendation
from app.services import audit, case_repo, hospital_config, slot_hold_service
from app.services.hms import effective_doctors_config

logger = logging.getLogger(__name__)

LOCKED_STATUSES = {"COMPLETED", "REJECTED"}
DOCTOR_FIXED_STATUSES = {"APPROVED", *LOCKED_STATUSES}


def patient_options(
    db: Session, case: PatientCase, routing: RoutingRecommendation, every: list[dict] | None = None
) -> tuple[list[dict], bool]:
    """`(times the patient is shown, whether they may pick the doctor)` out of `every` live time
    (looked up when not given). Times other cases hold stay listed, flagged `taken`, so the
    picker can grey them out. A red-flag case is offered nothing: it is told to come now."""
    if case.emergency_flagged_at is not None:
        return [], False
    shown = every if every is not None else slot_hold_service.live_options(db, get_hms(), routing, include_taken=True)
    if case_repo.session_for(db, case).status in DOCTOR_FIXED_STATUSES:
        return [s for s in shown if s.get("practitioner_id") == routing.doctor_id], False
    triage = case_repo.latest_triage(db, case.id)
    if not routing_rules.doctor_choice(triage.priority if triage else None):
        return routing_rules.one_per_time(shown, slot_hold_service.current_slot_id(routing)), False
    return shown, True


def _rostered(department_id: str, practitioner_id: str) -> bool:
    doctors = effective_doctors_config(hospital_config.load()).get("doctors") or []
    return any(d["id"] == practitioner_id and d.get("department_id") == department_id for d in doctors)


def select_slot(db: Session, case: PatientCase, slot_id: str) -> None:
    """Locked once the case is closed - by then a CareTask (or nothing) has already been drafted
    from whichever slot stood at finalize time."""
    session = case_repo.session_for(db, case)
    if case.emergency_flagged_at is not None:
        raise Conflict("This visit needs emergency care, so no appointment time is booked. Please go to the emergency department now.")
    if session.status in LOCKED_STATUSES:
        raise Conflict(f"The appointment slot cannot be changed while the case is {session.status}.")
    routing = case_repo.latest_routing(db, case.id)
    if routing is None:
        raise Unprocessable("No routing recommendation for this case yet.")
    # One pick per case at a time (two tabs): the second waits, then simply replaces the first,
    # instead of tripping the one-hold-per-case rule and being told another patient took it.
    routing = db.query(RoutingRecommendation).filter(RoutingRecommendation.id == routing.id).with_for_update().one()
    # Checked against the live list (see slot_hold_service.live_options), not the routing-time
    # snapshot, so a time freed since routing can be picked and a taken one cannot.
    every = slot_hold_service.live_options(db, get_hms(), routing, include_taken=True)
    shown, _ = patient_options(db, case, routing, every)
    if case.hms_appointment_id and slot_id == routing.selected_slot_id:
        return  # already booked at this time
    slot = next((s for s in shown if s.get("id") == slot_id), None)
    if slot is None:
        raise Conflict("That time is no longer available. Please pick another.")
    if slot["taken"]:  # greyed out in the picker; refused here too
        raise Conflict(slot_hold_service.TAKEN_MESSAGE)
    new_doctor = slot.get("practitioner_id")
    switching = bool(new_doctor) and new_doctor != routing.doctor_id
    if switching and not _rostered(routing.department_id, new_doctor):
        raise Conflict("That doctor is no longer taking appointments. Please pick another time.")
    # Every doctor's free times stay stored, not just the shown ones, so the next pick can still
    # move to any of them; the pick must be among them for the doctor calendar and finalize.
    options = [{k: v for k, v in s.items() if k != "taken"} for s in every if not s["taken"]]
    slot_hold_service.hold(db, case.id, slot, "patient")  # 409 if another case took it meanwhile
    if switching:
        audit.record(db, case.id, "patient", "routing.doctor_changed",
                     {"from": routing.doctor_id, "to": new_doctor, "slot_id": slot_id})
        routing.doctor_id, routing.doctor_name = new_doctor, slot.get("doctor_name")
        routing.rationale = routing_rules.with_doctor(routing.rationale, routing.doctor_name or new_doctor, "the patient's choice")
    routing.slot_options = options
    routing.selected_slot_id = slot_id
    previous = case.hms_appointment_id
    case.hms_appointment_id = _book(db, case, slot, routing.department_name)
    audit.record(db, case.id, "patient", "appointment.slot_selected", {"slot_id": slot_id})
    audit.record(db, case.id, "patient", "appointment.booked",
                 {"slot_id": slot_id, "practitioner_id": new_doctor, "hms_appointment_id": case.hms_appointment_id,
                  "replaces": previous})
    db.commit()
    if previous:
        cancel_booking(previous)


def _book(db: Session, case: PatientCase, slot: dict, department_name: str) -> str:
    """The appointment on the doctor's calendar. On failure nothing CareFlow wrote this request
    is kept, so the patient's earlier booking (if any) still stands."""
    if not case.hms_patient_id or not slot.get("practitioner_id"):
        db.rollback()
        raise Unprocessable("This visit is not linked to a hospital record yet, so it cannot be booked online.")
    name = case_repo.demographics(db, case.id).get("name") or "Patient"
    try:
        return get_hms().book_appointment(
            case.hms_patient_id, slot["practitioner_id"],
            datetime.fromisoformat(str(slot["start"])), datetime.fromisoformat(str(slot["end"])),
            f"Booked online via CareFlow ({department_name}) for {name}. Case {case.id}.",
        )
    except (httpx.HTTPError, ServiceUnavailable) as exc:
        db.rollback()
        logger.warning("Booking failed (%s)", type(exc).__name__)
        raise ServiceUnavailable("Could not book that time in the hospital system. Please try again or pick another.") from exc


def cancel_booking(reference: str) -> None:
    """Best effort: a booking that cannot be removed stays on the calendar for staff to clear,
    and is logged - it must never block the patient's new booking or a closed case."""
    try:
        get_hms().cancel_appointment(reference)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not cancel HMS appointment %s (%s)", reference, type(exc).__name__)


def release_booking(db: Session, case: PatientCase, actor: str) -> None:
    """A case that ends without a visit (rejected) gives its booked time back."""
    if not case.hms_appointment_id:
        return
    reference, case.hms_appointment_id = case.hms_appointment_id, None
    audit.record(db, case.id, actor, "appointment.cancelled", {"hms_appointment_id": reference})
    db.commit()
    cancel_booking(reference)
