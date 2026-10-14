"""Appointment slots for when the HMS has no real Slot resource to offer (this POC's OpenEMR
install has none): carved from the practitioner's published office hours when the HMS has them,
else a synthetic business-hours window. Advisory only, same as a real HMS slot - the patient's pick
still only becomes an appointment *request* at finalize time. Pure: no I/O, no clock of its own."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.integrations.hms.schemas import HMSSlot, HMSWeeklyHours

START_HOUR = 9
END_HOUR = 17
INTERVAL_MINUTES = 30
MAX_DAYS_AHEAD = 14
ALL_DAYS = {"mon", "tue", "wed", "thu", "fri"}
WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def chosen_slot(
    slot_options: list[dict], selected_slot_id: str | None, suggested_slot: dict | None
) -> dict | None:
    """Which offered slot stands for a case: the patient's pick if it's still among the
    options, else the sequential default. Shared by the doctor calendar (serializers.py) and
    the appointment request finalize.py sends to the HMS - both must agree on one slot."""
    return next((s for s in slot_options if s.get("id") == selected_slot_id), suggested_slot)


def slots_within_hours(
    hours: list[tuple[datetime, datetime]],
    busy: list[tuple[datetime, datetime]],
    department_id: str,
    practitioner_id: str,
    now: datetime,
    count: int = 8,
) -> list[HMSSlot]:
    """Half-hour slots inside the practitioner's published office hours (HMS "In Office"
    blocks), earliest first, skipping anything already past or overlapping a busy interval
    (an existing appointment). All datetimes must be timezone-aware."""
    slots: list[HMSSlot] = []
    step = timedelta(minutes=INTERVAL_MINUTES)
    for block_start, block_end in sorted(hours):
        slot_start = block_start
        while slot_start + step <= block_end and len(slots) < count:
            slot_end = slot_start + step
            if slot_start >= now and not any(b_start < slot_end and slot_start < b_end for b_start, b_end in busy):
                slots.append(HMSSlot(
                    id=f"hours-{practitioner_id}-{slot_start.strftime('%Y%m%dT%H%M')}",
                    practitioner_id=practitioner_id, department_id=department_id,
                    start=slot_start, end=slot_end,
                ))
            slot_start = slot_end
        if len(slots) >= count:
            break
    return slots


def fallback_slots(
    department_id: str, practitioner_id: str, working_days: list[str], now: datetime, count: int = 8
) -> list[HMSSlot]:
    """Half-hour slots within business hours on the practitioner's working days (FHIR mon/tue/...
    codes; empty defaults to weekdays). Once today's window is spent, rolls to the next working day."""
    days = {d.lower()[:3] for d in working_days} or ALL_DAYS
    slots: list[HMSSlot] = []
    cursor = now
    for _ in range(MAX_DAYS_AHEAD):
        if len(slots) >= count:
            break
        if cursor.strftime("%a").lower() in days:
            day_start = cursor.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
            day_end = cursor.replace(hour=END_HOUR, minute=0, second=0, microsecond=0)
            slot_start = day_start
            if cursor > day_start:
                steps = int((cursor - day_start).total_seconds() // 60 // INTERVAL_MINUTES) + 1
                slot_start = day_start + timedelta(minutes=steps * INTERVAL_MINUTES)
            while slot_start + timedelta(minutes=INTERVAL_MINUTES) <= day_end and len(slots) < count:
                slot_end = slot_start + timedelta(minutes=INTERVAL_MINUTES)
                slots.append(HMSSlot(
                    id=f"fallback-{practitioner_id}-{slot_start.strftime('%Y%m%dT%H%M')}",
                    practitioner_id=practitioner_id, department_id=department_id,
                    start=slot_start, end=slot_end,
                ))
                slot_start = slot_end
        cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return slots


def weekly_hours(blocks: list[tuple[datetime, datetime]]) -> list[HMSWeeklyHours]:
    """A practitioner's published office-hour blocks (clinic-local, aware) as a weekly pattern:
    days sharing identical hours grouped together, Monday first. Pass a window of at least a
    week so every working day is seen; a day's hours are the union of what it shows anywhere
    in the window."""
    by_day: dict[str, set[tuple[str, str]]] = {}
    for start, end in blocks:
        by_day.setdefault(start.strftime("%a").lower(), set()).add((start.strftime("%H:%M"), end.strftime("%H:%M")))
    groups: dict[tuple[tuple[str, str], ...], list[str]] = {}
    for day in WEEK:
        if day in by_day:
            groups.setdefault(tuple(sorted(by_day[day])), []).append(day)
    return sorted(
        (HMSWeeklyHours(days=days, times=[list(t) for t in times]) for times, days in groups.items()),
        key=lambda h: WEEK.index(h.days[0]),
    )
