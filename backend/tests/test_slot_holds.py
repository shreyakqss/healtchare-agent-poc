import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import Conflict
from app.db import SessionLocal
from app.integrations.hms import get_hms
from app.models import AuditEvent, IntakeSession, PatientCase, RoutingRecommendation, SlotHold, TriageResult
from app.services import appointment_service, doctor_load, lifecycle, slot_hold_service

DOCTOR = f"test-doctor-{uuid.uuid4().hex[:8]}"
BASE = datetime(2030, 1, 7, 10, 0, tzinfo=UTC)


def slot(minutes: int, practitioner: str = DOCTOR) -> dict:
    start = BASE + timedelta(minutes=minutes)
    return {"id": f"hours-{practitioner}-{start:%Y%m%dT%H%M}", "practitioner_id": practitioner,
            "department_id": "cardiology", "start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat()}


OPTIONS = [slot(0), slot(30), slot(60)]


@pytest.fixture
def make_case():
    session_ids = []

    def make(status: str = "NEEDS_REVIEW", doctor: str = DOCTOR, options: list | None = None) -> uuid.UUID:
        options = OPTIONS if options is None else options
        with SessionLocal() as db:
            session = IntakeSession(status=status, consent_status="GRANTED", channel="web")
            db.add(session)
            db.flush()
            case = PatientCase(session_id=session.id, hospital_id="qss-demo-clinic", hms_patient_id="test-mrn")
            db.add(case)
            db.flush()
            db.add(RoutingRecommendation(
                case_id=case.id, department_id="cardiology", department_name="Cardiology",
                doctor_id=doctor, doctor_name="Test Doctor", appointment_type_id="consult",
                appointment_type_label="Consult", rationale="test", matched_keywords=[],
                suggested_slot=options[0] if options else None, slot_options=options,
            ))
            db.commit()
            session_ids.append(session.id)
            return case.id

    yield make
    with SessionLocal() as db:
        db.query(IntakeSession).filter(IntakeSession.id.in_(session_ids)).delete(synchronize_session=False)
        db.commit()


@pytest.fixture(autouse=True)
def bookings(monkeypatch):
    """These tests are about holds, with made-up doctors OpenEMR has never heard of, so the
    calendar write is recorded instead (test_instant_booking.py books for real)."""
    from app.integrations.hms.openemr.client import FhirHMS

    made: list[str] = []
    cancelled: list[str] = []

    def book(self, mrn, practitioner_id, start, end, note):
        made.append(f"{practitioner_id}@{start.isoformat()}")
        return made[-1]

    monkeypatch.setattr(FhirHMS, "book_appointment", book)
    monkeypatch.setattr(FhirHMS, "cancel_appointment", lambda self, ref: cancelled.append(ref))
    return made, cancelled


def held(case_id) -> datetime | None:
    with SessionLocal() as db:
        row = db.query(SlotHold).filter(SlotHold.case_id == case_id).one_or_none()
        return row.slot_start if row else None


def test_second_patient_is_not_offered_or_defaulted_to_a_held_time(make_case):
    first, second = make_case(), make_case()
    with SessionLocal() as db:
        assert slot_hold_service.hold_first_free(db, first, OPTIONS, "test") == OPTIONS[0]
        db.commit()
    with SessionLocal() as db:
        offered = slot_hold_service.free_of_holds(db, OPTIONS, second)
        assert offered == OPTIONS[1:]
        assert slot_hold_service.hold_first_free(db, second, offered, "test") == OPTIONS[1]
        db.commit()
    assert held(first) == BASE and held(second) == BASE + timedelta(minutes=30)


def test_picking_a_time_another_case_holds_is_a_conflict(make_case):
    first, second = make_case(), make_case()
    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, first), OPTIONS[2]["id"])
    with SessionLocal() as db:
        with pytest.raises(Conflict):
            appointment_service.select_slot(db, db.get(PatientCase, second), OPTIONS[2]["id"])
        assert db.query(RoutingRecommendation).filter_by(case_id=second).one().selected_slot_id is None


def test_confirming_books_and_changing_moves_the_booking(make_case, bookings):
    made, cancelled = bookings
    case_id = make_case()
    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, case_id), OPTIONS[0]["id"])
        appointment_service.select_slot(db, db.get(PatientCase, case_id), OPTIONS[0]["id"])  # same time: no-op
        appointment_service.select_slot(db, db.get(PatientCase, case_id), OPTIONS[1]["id"])
    with SessionLocal() as db:
        assert db.get(PatientCase, case_id).hms_appointment_id == made[-1]
    assert len(made) == 2 and cancelled == [made[0]]


def test_changing_a_pick_frees_the_old_time(make_case):
    first, second = make_case(), make_case()
    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, first), OPTIONS[0]["id"])
    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, first), OPTIONS[1]["id"])
    with SessionLocal() as db:
        appointment_service.select_slot(db, db.get(PatientCase, second), OPTIONS[0]["id"])
    assert held(first) == BASE + timedelta(minutes=30) and held(second) == BASE


def test_simultaneous_picks_of_one_time_cannot_both_win(make_case):
    cases = [make_case() for _ in range(4)]
    barrier = threading.Barrier(len(cases))
    outcomes: list[str] = []

    def pick(case_id):
        with SessionLocal() as db:
            case = db.get(PatientCase, case_id)
            barrier.wait()
            try:
                appointment_service.select_slot(db, case, OPTIONS[1]["id"])
                outcomes.append("won")
            except Conflict:
                outcomes.append("taken")

    threads = [threading.Thread(target=pick, args=(c,)) for c in cases]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["taken", "taken", "taken", "won"]


def test_rejecting_a_case_releases_its_time_and_completing_keeps_it(make_case):
    rejected, completed = make_case(), make_case("APPROVED")
    with SessionLocal() as db:
        slot_hold_service.hold(db, rejected, OPTIONS[0], "test")
        slot_hold_service.hold(db, completed, OPTIONS[1], "test")
        db.commit()
    with SessionLocal() as db:
        for case_id, target in ((rejected, "REJECTED"), (completed, "COMPLETED")):
            case = db.get(PatientCase, case_id)
            lifecycle.transition(db, db.get(IntakeSession, case.session_id), target, "test", case_id)
    assert held(rejected) is None
    assert held(completed) == BASE + timedelta(minutes=30)
    later = make_case()
    with SessionLocal() as db:
        assert slot_hold_service.free_of_holds(db, OPTIONS, later) == [OPTIONS[0], OPTIONS[2]]


def test_moving_to_a_doctorless_time_releases_the_old_hold(make_case):
    case_id = make_case()
    with SessionLocal() as db:
        slot_hold_service.hold(db, case_id, OPTIONS[0], "test")
        slot_hold_service.hold(db, case_id, {**OPTIONS[1], "practitioner_id": None}, "test")
        db.commit()
    assert held(case_id) is None


def test_one_patient_picking_twice_at_once_is_not_told_someone_else_took_it(make_case):
    case_id = make_case()
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def pick(slot_id):
        with SessionLocal() as db:
            case = db.get(PatientCase, case_id)
            barrier.wait()
            try:
                appointment_service.select_slot(db, case, slot_id)
            except Exception as exc:  # noqa: BLE001 - any failure is the bug
                errors.append(exc)

    threads = [threading.Thread(target=pick, args=(o["id"],)) for o in OPTIONS[:2]]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with SessionLocal() as db:
        selected = db.query(RoutingRecommendation).filter_by(case_id=case_id).one().selected_slot_id
    assert held(case_id) == datetime.fromisoformat(next(o for o in OPTIONS if o["id"] == selected)["start"])


def test_a_failed_case_releases_its_time(make_case):
    case_id = make_case("ANALYZING")
    with SessionLocal() as db:
        slot_hold_service.hold(db, case_id, OPTIONS[0], "test")
        db.commit()
    with SessionLocal() as db:
        case = db.get(PatientCase, case_id)
        lifecycle.transition(db, db.get(IntakeSession, case.session_id), "FAILED", "test", case_id)
    assert held(case_id) is None


@pytest.fixture
def doctor_with_hours():
    """A live OpenEMR practitioner with published office hours, and their open times."""
    hms = get_hms()
    for practitioner in hms.list_practitioners(include_usernames=False):
        slots = [s.model_dump(mode="json") for s in hms.available_slots(practitioner.department_id, practitioner.id, limit=20)]
        if len(slots) >= 4 and slots[0]["id"].startswith("hours-"):
            return practitioner, slots
    pytest.skip("no OpenEMR practitioner with office hours")


def routing_of(db, case_id) -> RoutingRecommendation:
    return db.query(RoutingRecommendation).filter_by(case_id=case_id).one()


def test_a_time_freed_after_routing_comes_back_and_can_be_picked(make_case, doctor_with_hours):
    practitioner, live = doctor_with_hours
    with SessionLocal() as db:
        free = slot_hold_service.free_of_holds(db, live, None)
    target = free[0]
    first = make_case(doctor=practitioner.id, options=free[:3])
    second = make_case(doctor=practitioner.id, options=free[1:4])  # routed while `target` was held
    with SessionLocal() as db:
        slot_hold_service.hold(db, first, target, "test")
        db.commit()
    with SessionLocal() as db:
        assert target["id"] not in [s["id"] for s in slot_hold_service.live_options(db, get_hms(), routing_of(db, second))]
        slot_hold_service.release(db, first, "test")
        db.commit()
    with SessionLocal() as db:
        assert target["id"] in [s["id"] for s in slot_hold_service.live_options(db, get_hms(), routing_of(db, second))]
        appointment_service.select_slot(db, db.get(PatientCase, second), target["id"])
    with SessionLocal() as db:
        routing = routing_of(db, second)
        assert routing.selected_slot_id == target["id"]
        assert any(s["id"] == target["id"] for s in routing.slot_options)  # calendar + finalize resolve it here
    assert held(second) == datetime.fromisoformat(target["start"])


def test_a_time_taken_after_routing_drops_out_and_cannot_be_picked(make_case, doctor_with_hours):
    practitioner, live = doctor_with_hours
    with SessionLocal() as db:
        free = slot_hold_service.free_of_holds(db, live, None)
    target = free[1]
    mine = make_case(doctor=practitioner.id, options=free[:4])  # routed while `target` was free
    other = make_case(doctor=practitioner.id, options=free[:4])
    with SessionLocal() as db:
        slot_hold_service.hold(db, mine, free[0], "test")
        slot_hold_service.hold(db, other, target, "test")
        db.commit()
    with SessionLocal() as db:
        ids = [s["id"] for s in slot_hold_service.live_options(db, get_hms(), routing_of(db, mine))]
        assert target["id"] not in ids and free[0]["id"] in ids  # my own time stays listed
        shown = slot_hold_service.live_options(db, get_hms(), routing_of(db, mine), include_taken=True)
        flags = {s["id"]: s["taken"] for s in shown}
        assert flags[target["id"]] is True and flags[free[0]["id"]] is False  # greyed out, not hidden
        assert sum(not taken for taken in flags.values()) == 8  # still 8 pickable times
        with pytest.raises(Conflict):
            appointment_service.select_slot(db, db.get(PatientCase, mine), target["id"])
    assert held(mine) == datetime.fromisoformat(free[0]["start"])


# --- two doctors in one department --------------------------------------------------------

OTHER = f"test-doctor-{uuid.uuid4().hex[:8]}"


def named(minutes: int, practitioner: str, name: str) -> dict:
    return {**slot(minutes, practitioner), "doctor_name": name}


# DOCTOR is assigned (earliest, 10:00); OTHER is free at 10:00 too, and at 10:30.
TWO = [named(0, DOCTOR, "Test Doctor"), named(0, OTHER, "Other Doctor"), named(30, OTHER, "Other Doctor"),
       named(60, DOCTOR, "Test Doctor")]


def triaged(case_id, priority: str) -> None:
    with SessionLocal() as db:
        db.add(TriageResult(case_id=case_id, priority=priority, rule_ids=[], rule_codes=[], warnings=[], evidence=[]))
        db.commit()


def test_picking_another_doctors_time_moves_the_case_to_that_doctor(make_case, monkeypatch):
    monkeypatch.setattr(appointment_service, "_rostered", lambda department_id, pid: True)
    case = make_case(options=TWO)
    triaged(case, "low")
    with SessionLocal() as db:
        shown, choice = appointment_service.patient_options(db, db.get(PatientCase, case), routing_of(db, case))
        assert choice and {s["practitioner_id"] for s in shown} == {DOCTOR, OTHER}
        appointment_service.select_slot(db, db.get(PatientCase, case), TWO[2]["id"])
    with SessionLocal() as db:
        routing = routing_of(db, case)
        assert (routing.doctor_id, routing.doctor_name) == (OTHER, "Other Doctor")
        assert routing.rationale.endswith("Assigned to Other Doctor (the patient's choice).")
        assert {s["practitioner_id"] for s in routing.slot_options} == {DOCTOR, OTHER}  # can switch back
        changed = db.query(AuditEvent).filter_by(case_id=case, action="routing.doctor_changed").one()
        assert changed.payload["from"] == DOCTOR and changed.payload["to"] == OTHER
    with SessionLocal() as db:  # and back again
        appointment_service.select_slot(db, db.get(PatientCase, case), TWO[3]["id"])
    with SessionLocal() as db:
        assert routing_of(db, case).doctor_id == DOCTOR
    assert held(case) == BASE + timedelta(minutes=60)


def test_an_urgent_patient_sees_one_time_each_and_cannot_pick_the_doctor(make_case, monkeypatch):
    monkeypatch.setattr(appointment_service, "_rostered", lambda department_id, pid: True)
    case = make_case(options=TWO)
    triaged(case, "high")
    with SessionLocal() as db:
        shown, choice = appointment_service.patient_options(db, db.get(PatientCase, case), routing_of(db, case))
        assert not choice
        assert [s["id"] for s in shown] == [TWO[0]["id"], TWO[2]["id"], TWO[3]["id"]]  # one per time, own kept
        with pytest.raises(Conflict):  # the same time with the other doctor is not offered
            appointment_service.select_slot(db, db.get(PatientCase, case), TWO[1]["id"])
    with SessionLocal() as db:  # an earliest-at-that-time pick may still land on the other doctor
        appointment_service.select_slot(db, db.get(PatientCase, case), TWO[2]["id"])
    with SessionLocal() as db:
        assert routing_of(db, case).doctor_id == OTHER


def test_once_approved_only_the_assigned_doctors_times_are_offered(make_case):
    case = make_case(status="APPROVED", options=TWO)
    triaged(case, "low")
    with SessionLocal() as db:
        shown, choice = appointment_service.patient_options(db, db.get(PatientCase, case), routing_of(db, case))
        assert not choice and {s["practitioner_id"] for s in shown} == {DOCTOR}
        with pytest.raises(Conflict):
            appointment_service.select_slot(db, db.get(PatientCase, case), TWO[2]["id"])
    with SessionLocal() as db:
        assert routing_of(db, case).doctor_id == DOCTOR
    assert held(case) is None


def test_a_doctor_who_left_the_roster_cannot_be_picked(make_case, monkeypatch):
    monkeypatch.setattr(appointment_service, "_rostered", lambda department_id, pid: pid == DOCTOR)
    case = make_case(options=TWO)
    with SessionLocal() as db:
        with pytest.raises(Conflict, match="no longer taking appointments"):
            appointment_service.select_slot(db, db.get(PatientCase, case), TWO[2]["id"])
    with SessionLocal() as db:
        assert routing_of(db, case).doctor_id == DOCTOR
    assert held(case) is None


def test_open_cases_count_only_unfinished_cases_routed_to_the_doctor(make_case):
    make_case(), make_case(status="APPROVED"), make_case(status="COMPLETED"), make_case(status="REJECTED")
    make_case(doctor=OTHER)
    with SessionLocal() as db:
        assert doctor_load.open_case_counts(db, [DOCTOR, OTHER]) == {DOCTOR: 2, OTHER: 1}
