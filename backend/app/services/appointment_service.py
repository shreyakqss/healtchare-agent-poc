"""Patient's pick among the doctor's currently open advisory slots."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unprocessable
from app.integrations.hms import get_hms
from app.models import PatientCase, RoutingRecommendation
from app.services import audit, case_repo, slot_hold_service

LOCKED_STATUSES = {"COMPLETED", "REJECTED"}


def select_slot(db: Session, case: PatientCase, slot_id: str) -> None:
    """Locked once the case is closed - by then a CareTask (or nothing) has already been drafted
    from whichever slot stood at finalize time."""
    session = case_repo.session_for(db, case)
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
    shown = slot_hold_service.live_options(db, get_hms(), routing, include_taken=True)
    slot = next((s for s in shown if s.get("id") == slot_id), None)
    if slot is None:
        raise Conflict("That time is no longer available. Please pick another.")
    if slot["taken"]:  # greyed out in the picker; refused here too
        raise Conflict(slot_hold_service.TAKEN_MESSAGE)
    options = [{k: v for k, v in s.items() if k != "taken"} for s in shown if not s["taken"]]
    slot_hold_service.hold(db, case.id, slot, "patient")  # 409 if another case took it meanwhile
    # The stored options must contain the pick: the doctor calendar and finalize resolve it there.
    routing.slot_options = options
    routing.selected_slot_id = slot_id
    audit.record(db, case.id, "patient", "appointment.slot_selected", {"slot_id": slot_id})
    db.commit()
