from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain import scheduling
from app.integrations.hms.openemr.client import _office_hours_and_busy

IST = ZoneInfo("Asia/Kolkata")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def starts(slots) -> list[datetime]:
    return [s.start for s in slots]


def test_slots_fill_office_hours_in_half_hours_earliest_first():
    hours = [(at(15, 17), at(15, 18)), (at(15, 11), at(15, 12))]
    slots = scheduling.slots_within_hours(hours, [], "general_medicine", "p1", at(15, 8))
    assert starts(slots) == [at(15, 11), at(15, 11, 30), at(15, 17), at(15, 17, 30)]
    assert all(s.practitioner_id == "p1" and s.department_id == "general_medicine" for s in slots)


def test_slots_skip_the_past_and_booked_time():
    hours = [(at(15, 11), at(15, 14))]
    busy = [(at(15, 12, 15), at(15, 12, 45))]  # overlaps both 12:00 and 12:30
    slots = scheduling.slots_within_hours(hours, busy, "d", "p1", at(15, 11, 10))
    assert starts(slots) == [at(15, 11, 30), at(15, 13), at(15, 13, 30)]


def test_slots_stop_at_count():
    hours = [(at(15, 11), at(15, 14)), (at(16, 11), at(16, 14))]
    assert len(scheduling.slots_within_hours(hours, [], "d", "p1", at(15, 0), count=8)) == 8


def test_openemr_calendar_rows_split_into_office_hours_and_bookings():
    def row(**kw):
        return {"pce_aid_uuid": "p1", "pc_eventDate": "2026-10-15", "pc_pid": "", "pc_apptstatus": "-", **kw}

    events = [
        row(pc_catid="2", pc_startTime="11:00:00", pc_endTime="14:00:00"),            # In Office
        row(pc_catid="5", pc_pid="7", pc_startTime="12:00:00", pc_endTime="12:15:00"),  # booked
        row(pc_catid="5", pc_pid="8", pc_apptstatus="x", pc_startTime="13:00:00", pc_endTime="13:15:00"),  # cancelled
        row(pc_catid="2", pce_aid_uuid="p2", pc_startTime="09:00:00", pc_endTime="10:00:00"),  # someone else
        row(pc_catid="2", pc_startTime="bad", pc_endTime="10:00:00"),                    # unparseable
    ]
    hours, busy = _office_hours_and_busy(events, "p1", IST)
    assert hours == [(at(15, 11), at(15, 14))]
    assert busy == [(at(15, 12), at(15, 12, 15))]


def test_weekly_hours_groups_days_sharing_the_same_hours_monday_first():
    # 2026-10-12 is a Monday. Two weeks, so a missed day in one week still shows up.
    blocks = []
    for week in (0, 7):
        for day in (12, 13, 14, 15, 16):  # Mon-Fri, split shift
            blocks += [(at(day + week, 10), at(day + week, 13)), (at(day + week, 16), at(day + week, 19))]
        blocks.append((at(17 + week, 9), at(17 + week, 12)))  # Saturday morning only
    hours = scheduling.weekly_hours(blocks)
    assert [(h.days, h.times) for h in hours] == [
        (["mon", "tue", "wed", "thu", "fri"], [["10:00", "13:00"], ["16:00", "19:00"]]),
        (["sat"], [["09:00", "12:00"]]),
    ]
    assert scheduling.weekly_hours([]) == []
