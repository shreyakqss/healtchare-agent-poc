"""Patient's pick among the advisory slots the care navigator offered at routing time."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import Conflict, Unprocessable
from app.models import PatientCase
from app.services import audit, case_repo

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
    if not any(s.get("id") == slot_id for s in (routing.slot_options or [])):
        raise Unprocessable("That slot was not one of the offered options.")
    routing.selected_slot_id = slot_id
    audit.record(db, case.id, "patient", "appointment.slot_selected", {"slot_id": slot_id})
    db.commit()
