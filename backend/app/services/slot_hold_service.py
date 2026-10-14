"""Keeps two open cases off the same practitioner at the same time.

CareFlow never books in the HMS calendar (an appointment *request* is a chart note), so the
HMS cannot tell CareFlow which times its own cases already took. A `SlotHold` row is that
record: one per case, unique per (practitioner, start). The unique index is the guard, so two
patients picking the same time at the same instant cannot both win.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.domain import scheduling
from app.models import RoutingRecommendation, SlotHold
from app.services import audit

logger = logging.getLogger(__name__)

TAKEN_MESSAGE = "That time was just taken by another patient. Please pick another."


def _start(slot: dict) -> datetime:
    return datetime.fromisoformat(str(slot["start"]))


def held_starts(db: Session, practitioner_id: str, excluding_case: uuid.UUID | None = None) -> set[datetime]:
    """Start times other cases already hold with this practitioner."""
    query = db.query(SlotHold.slot_start).filter(SlotHold.practitioner_id == practitioner_id)
    if excluding_case is not None:
        query = query.filter(SlotHold.case_id != excluding_case)
    return {row.slot_start for row in query}


def mark_taken(db: Session, slots: list[dict], case_id: uuid.UUID | None) -> list[dict]:
    """Each slot with `taken` set when another case holds that practitioner at that time."""
    held: dict[str, set[datetime]] = {}
    marked = []
    for slot in slots:
        pid = slot.get("practitioner_id")
        if pid and pid not in held:
            held[pid] = held_starts(db, pid, excluding_case=case_id)
        marked.append({**slot, "taken": bool(pid) and _start(slot) in held[pid]})
    return marked


def free_of_holds(db: Session, slots: list[dict], case_id: uuid.UUID | None) -> list[dict]:
    """The offered slots minus any another case holds with the same practitioner."""
    return [_unflagged(s) for s in mark_taken(db, slots, case_id) if not s["taken"]]


def _unflagged(slot: dict) -> dict:
    return {k: v for k, v in slot.items() if k != "taken"}


def _first_free(marked: list[dict], limit: int, include_taken: bool) -> list[dict]:
    """Up to `limit` free slots; with `include_taken`, the taken ones among them stay in place."""
    out, free = [], 0
    for slot in marked:
        if free >= limit:
            break
        if slot["taken"]:
            if include_taken:
                out.append(slot)
            continue
        out.append(slot if include_taken else _unflagged(slot))
        free += 1
    return out


def open_slots(
    db: Session, hms, department_id: str, practitioner_id: str | None, limit: int,
    excluding_case: uuid.UUID | None = None, include_taken: bool = False,
) -> list[dict]:
    """The HMS's open slots for a practitioner, `limit` of them free of other cases' holds.
    `include_taken` keeps the held ones too, flagged `taken`, so a picker can grey them out."""
    held = len(held_starts(db, practitioner_id, excluding_case)) if practitioner_id else 0
    slots = hms.available_slots(department_id, practitioner_id, limit=limit + held)
    marked = mark_taken(db, [s.model_dump(mode="json") for s in slots], excluding_case)
    return _first_free(marked, limit, include_taken)


def live_options(
    db: Session, hms, routing: RoutingRecommendation, count: int = 8, include_taken: bool = False
) -> list[dict]:
    """What the patient can pick from *now*, not the snapshot taken at routing: the doctor's
    current open times, so a freed time comes back and a newly taken one is excluded - or, with
    `include_taken`, kept and flagged `taken`. The case's own current time always stays listed.
    If the HMS cannot answer, the routing-time snapshot stands in."""
    stored = routing.slot_options or []
    if not routing.doctor_id:
        return [{**s, "taken": False} for s in stored] if include_taken else stored
    try:
        live = open_slots(db, hms, routing.department_id, routing.doctor_id, count,
                          excluding_case=routing.case_id, include_taken=include_taken)
    except httpx.HTTPError as exc:
        logger.warning("live slots unavailable, using routing-time options (%s)", type(exc).__name__)
        live = []
    if not live:
        live = _first_free(mark_taken(db, stored, routing.case_id), count, include_taken)
    current = scheduling.chosen_slot(stored, routing.selected_slot_id, routing.suggested_slot)
    if current and all(s.get("id") != current.get("id") for s in live):
        current = {**_unflagged(current), "taken": False} if include_taken else _unflagged(current)
        live = sorted([current, *live], key=_start)
    return live


def current_slot_id(routing: RoutingRecommendation) -> str | None:
    """The slot standing for the case: the pick, else the held default."""
    current = scheduling.chosen_slot(routing.slot_options or [], routing.selected_slot_id, routing.suggested_slot)
    return current.get("id") if current else None


def hold(db: Session, case_id: uuid.UUID, slot: dict, actor: str) -> None:
    """Make `slot` this case's one held time, replacing any earlier hold. A slot with no
    practitioner cannot be held, so it only drops the old hold. Raises Conflict if another
    case holds it; the caller's transaction is left usable either way."""
    pid = slot.get("practitioner_id")
    if not pid:
        release(db, case_id, actor)
        return
    start = _start(slot)
    existing = db.query(SlotHold).filter(SlotHold.case_id == case_id).one_or_none()
    if existing is not None and existing.practitioner_id == pid and existing.slot_start == start:
        return
    try:
        with db.begin_nested():
            if existing is not None:
                db.delete(existing)
                db.flush()
            db.add(SlotHold(case_id=case_id, practitioner_id=pid, slot_start=start))
            db.flush()
    except IntegrityError as exc:
        raise Conflict(TAKEN_MESSAGE) from exc
    audit.record(db, case_id, actor, "appointment.slot_held",
                 {"practitioner_id": pid, "slot_start": start.isoformat()})


def hold_first_free(db: Session, case_id: uuid.UUID, slots: list[dict], actor: str) -> dict | None:
    """Hold the earliest slot nobody else took, skipping any lost to a concurrent case."""
    for slot in slots:
        try:
            hold(db, case_id, slot, actor)
            return slot
        except Conflict:
            continue
    return None


def release(db: Session, case_id: uuid.UUID, actor: str) -> None:
    """Drop the case's hold, if any. Rejected and failed cases, and a re-route that ends up
    holding no time, must not keep blocking a time no screen shows for them."""
    existing = db.query(SlotHold).filter(SlotHold.case_id == case_id).one_or_none()
    if existing is None:
        return
    db.delete(existing)
    audit.record(db, case_id, actor, "appointment.slot_released",
                 {"practitioner_id": existing.practitioner_id, "slot_start": existing.slot_start.isoformat()})
