"""Admin > Doctors. The rules are unit tests; the onboarding itself runs against the live
OpenEMR and Keycloak (test instances only) and removes every doctor it creates."""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.errors import Conflict, Forbidden, NotFound, ServiceUnavailable, Unprocessable
from app.db import SessionLocal
from app.domain import provider as rules
from app.integrations.hms import get_hms
from app.integrations.hms.openemr import provisioning
from app.integrations.keycloak import admin_client
from app.main import app
from app.models import AdminAuditEvent
from app.schemas.requests import ChangeHoursRequest, NewDoctorRequest, UpdateDoctorRequest
from app.security import CurrentPrincipal, authenticate
from app.services import doctor_onboarding_service as onboarding
from tests.helpers import BASE

CLINIC = "qss-demo-clinic"
PASSWORD = "Onboard#2026x"


def admin(clinic_id: str | None = CLINIC) -> CurrentPrincipal:
    user_id = uuid.uuid4()
    return CurrentPrincipal(user_id=user_id, subject=str(user_id), roles=frozenset({"admin"}),
                            username="test.admin", clinic_id=clinic_id, auth_method="test")


def form(**overrides) -> NewDoctorRequest:
    tag = uuid.uuid4().hex[:8]
    values = dict(
        first_name="Test", last_name=f"Doctor{tag}", email=f"onboard-{tag}@example.test",
        username=f"testdoc{tag}", password=PASSWORD, department_id="cardiology",
        specialty_code="207RC0000X", days=["mon", "wed", "fri"], ranges=[("10:00", "13:00"), ("16:00", "18:00")],
        start_date=date.today(), weeks=2,
    )
    return NewDoctorRequest(**{**values, **overrides})


# --- rules (no I/O) ----------------------------------------------------------------------

def test_npi_check_digit():
    assert rules.npi_is_valid("1234567893")  # CMS's worked example
    assert not rules.npi_is_valid("1234567890")
    assert not rules.npi_is_valid("12345")
    assert rules.npi_from("123456789") == "1234567893"


def test_onboarding_generates_the_npi_and_never_takes_one():
    with pytest.raises(ValueError):
        NewDoctorRequest(**{**form().model_dump(), "npi": "1234567893"})
    npis = {onboarding._new_npi() for _ in range(5)} if provisioning.configured() else set()
    assert all(rules.npi_is_valid(n) and n[0] in "12" for n in npis)


def test_password_follows_openemr_secure_password_rule():
    assert rules.password_problem("Onboard#2026x", "testdoc") is None
    assert rules.password_problem("short1A", "x")  # too short
    assert rules.password_problem("alllowercase", "x")  # one class only
    assert rules.password_problem("Testdoc#2026", "testdoc")  # contains the username


def test_hours_are_checked_and_expanded_one_row_per_day_and_range():
    assert rules.hours_problems(["mon"], [("10:00", "13:00"), ("12:00", "14:00")]) == ["Time ranges overlap."]
    assert rules.hours_problems([], [("10:00", "13:00")]) == ["Pick at least one working day."]
    assert rules.hours_problems(["mon"], [("13:00", "10:00")])
    assert rules.hours_problems(["mon"], [("05:00", "10:00")])
    monday = date(2030, 1, 7)
    blocks = rules.expand_hours(["mon", "fri"], [("16:00", "19:00"), ("10:00", "13:00")], monday, 2)
    assert len(blocks) == 8
    assert blocks[0] == (monday, time(10), time(13)) and blocks[-1][0] == monday + timedelta(days=11)


def test_extending_repeats_the_last_week_day_by_day():
    monday = date(2030, 1, 7)
    published = [(monday, time(10), time(13)), (monday + timedelta(days=2), time(16), time(19))]
    more = rules.repeat_last_week(published, 2)
    assert more == [
        (monday + timedelta(days=7), time(10), time(13)), (monday + timedelta(days=9), time(16), time(19)),
        (monday + timedelta(days=14), time(10), time(13)), (monday + timedelta(days=16), time(16), time(19)),
    ]


def test_role_code_falls_back_to_the_parent_specialty():
    roles = {"207R00000X", "207X00000X"}
    assert rules.role_code_for("207X00000X", roles) == "207X00000X"
    assert rules.role_code_for("207RC0000X", roles) == "207R00000X"
    assert rules.role_code_for("208600000X", roles) == rules.GENERIC_ROLE


def test_admin_without_a_hospital_cannot_manage_doctors():
    with pytest.raises(Forbidden):
        onboarding.clinic_for(admin(None))
    with pytest.raises(Forbidden):
        onboarding.clinic_for(admin("no-such-hospital"))


def test_only_admins_reach_the_doctor_endpoints():
    client = TestClient(app)
    for role in ("patient", "clinician"):
        principal = admin()
        app.dependency_overrides[authenticate] = lambda p=principal, r=role: CurrentPrincipal(
            user_id=p.user_id, subject=p.subject, roles=frozenset({r}), clinic_id=CLINIC, auth_method="test")
        assert client.get(f"{BASE}/admin/doctors").status_code == 403
        assert client.post(f"{BASE}/admin/doctors", json=form().model_dump(mode="json")).status_code == 403
        change = {"days": ["mon"], "ranges": [["10:00", "12:00"]], "start_date": str(date.today()), "weeks": 1}
        assert client.put(f"{BASE}/admin/doctors/1/hours", json=change).status_code == 403
        assert client.post(f"{BASE}/admin/doctors/1/hours/preview", json=change).status_code == 403
    client.close()


# --- live OpenEMR + Keycloak --------------------------------------------------------------

def _live_or_skip():
    if not provisioning.configured():
        pytest.skip("OPENEMR_MYSQL_USER/PASSWORD are not set in backend/.env")
    try:
        admin_client.username_or_email_taken("careflow-probe", "probe@example.test")
    except ServiceUnavailable:
        pytest.skip("Keycloak admin API unreachable")


@pytest.fixture
def created():
    """Usernames to remove from both systems after the test."""
    _live_or_skip()
    usernames: list[str] = []
    yield usernames
    for username in usernames:
        for p in provisioning.providers(3):
            if p.username == username:
                provisioning.delete_provider(p.id)
        base, headers = admin_client._admin()
        import httpx
        for user in httpx.get(f"{base}/users", params={"username": username, "exact": "true"}, headers=headers).json():
            admin_client.delete_user(user["id"])
    with SessionLocal() as db:
        db.query(AdminAuditEvent).filter(AdminAuditEvent.actor == "admin:test.admin").delete()
        db.commit()


@pytest.mark.integration
def test_a_new_doctor_can_log_in_is_routed_and_has_bookable_times(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
    assert doctor["department_id"] == "cardiology" and doctor["has_login"] is True
    assert doctor["hours"] == [{"days": ["mon", "wed", "fri"], "times": [["10:00", "13:00"], ["16:00", "18:00"]]}]
    hms = get_hms()
    # The same OpenEMR password check a doctor's review/approve goes through.
    assert hms.verify_credentials(new.username, PASSWORD).id == doctor["practitioner_id"]
    live = next(p for p in hms.list_practitioners() if p.id == doctor["practitioner_id"])
    assert live.department_id == "cardiology" and live.username == new.username
    assert hms.available_slots("cardiology", doctor["practitioner_id"], limit=2)
    with SessionLocal() as db:
        event = db.query(AdminAuditEvent).filter(AdminAuditEvent.action == "doctor.created",
                                                 AdminAuditEvent.payload["username"].astext == new.username).one()
        assert event.clinic_id == CLINIC and PASSWORD not in str(event.payload)


@pytest.mark.integration
def test_duplicates_and_bad_details_are_refused_before_anything_is_written(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        onboarding.create(db, admin(), new)
    again = form(username=new.username, email=new.email)
    found = onboarding.problems(onboarding.clinic_for(admin()), again)
    assert "That username is already used in the hospital system." in found
    bad = form(specialty_code="207X00000X")
    with SessionLocal() as db, pytest.raises(Unprocessable):
        onboarding.create(db, admin(), bad)
    assert provisioning.clashes(bad.username) == []


@pytest.mark.integration
def test_a_failed_login_step_leaves_no_half_created_doctor(created, monkeypatch):
    new = form()
    created.append(new.username)

    def fail(*_, **__):
        raise ServiceUnavailable("simulated Keycloak failure")

    issued: list[str] = []
    real_new_npi = onboarding._new_npi
    monkeypatch.setattr(onboarding, "_new_npi", lambda: issued.append(real_new_npi()) or issued[-1])
    monkeypatch.setattr(admin_client, "create_clinician", fail)
    with SessionLocal() as db, pytest.raises(ServiceUnavailable):
        onboarding.create(db, admin(), new)
    assert issued and provisioning.clashes(new.username, issued[0]) == []


@pytest.mark.integration
def test_extend_hours_continues_the_pattern_and_stays_inside_the_hospital(created):
    new = form(weeks=1)
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
        extended = onboarding.extend_hours(db, admin(), doctor["id"], 2)
    assert date.fromisoformat(str(extended["hours_until"])) == date.fromisoformat(str(doctor["hours_until"])) + timedelta(days=14)
    with SessionLocal() as db, pytest.raises(NotFound):
        onboarding.extend_hours(db, admin(), 1, 1)  # OpenEMR's own admin account is not a doctor here


# --- removal ------------------------------------------------------------------------------

def _case_routed_to(practitioner_id: str, status: str):
    from app.models import IntakeSession, PatientCase, RoutingRecommendation
    with SessionLocal() as db:
        session = IntakeSession(status=status, consent_status="GRANTED", channel="web")
        db.add(session)
        db.flush()
        case = PatientCase(session_id=session.id, hospital_id=CLINIC)
        db.add(case)
        db.flush()
        db.add(RoutingRecommendation(
            case_id=case.id, department_id="cardiology", department_name="Cardiology", doctor_id=practitioner_id,
            doctor_name="Test", appointment_type_id="consult", appointment_type_label="Consult", rationale="test",
            matched_keywords=[], suggested_slot=None, slot_options=[],
        ))
        db.commit()
        return session.id


def _drop_session(session_id):
    from app.models import IntakeSession
    with SessionLocal() as db:
        db.query(IntakeSession).filter(IntakeSession.id == session_id).delete()
        db.commit()


@pytest.mark.integration
def test_a_never_used_doctor_is_erased_from_both_systems(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
        assert onboarding.removal_check(db, admin(), doctor["id"])["mode"] == "delete"
        assert onboarding.remove(db, admin(), doctor["id"])["result"] == "deleted"
    assert provisioning.clashes(new.username, doctor["npi"]) == []
    assert not admin_client.username_or_email_taken(new.username, new.email)


@pytest.mark.integration
def test_a_doctor_with_history_is_deactivated_then_reactivated(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
    past = _case_routed_to(doctor["practitioner_id"], "COMPLETED")
    try:
        with SessionLocal() as db:
            check = onboarding.removal_check(db, admin(), doctor["id"])
            assert check["mode"] == "deactivate" and check["history"]["cases"] == 1
            result = onboarding.remove(db, admin(), doctor["id"])
        assert result["result"] == "deactivated" and result["doctor"]["active"] is False
        hms = get_hms()
        assert doctor["practitioner_id"] not in [p.id for p in hms.list_practitioners()]  # never routed again
        assert hms.verify_credentials(new.username, PASSWORD) is None  # cannot sign off any more
        with SessionLocal() as db:
            back = onboarding.reactivate(db, admin(), doctor["id"])
        assert back["active"] is True and back["hours"] == doctor["hours"]  # schedule restored
        assert hms.verify_credentials(new.username, PASSWORD) is not None
        assert doctor["practitioner_id"] in [p.id for p in hms.list_practitioners()]
    finally:
        _drop_session(past)


@pytest.mark.integration
def test_open_cases_block_removal(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
    open_case = _case_routed_to(doctor["practitioner_id"], "NEEDS_REVIEW")
    try:
        with SessionLocal() as db:
            assert onboarding.removal_check(db, admin(), doctor["id"])["blocked_by_open_cases"] == 1
            with pytest.raises(Conflict):
                onboarding.remove(db, admin(), doctor["id"])
        assert provisioning.provider(3, doctor["id"]).active
    finally:
        _drop_session(open_case)


# --- hours: editable by admins only ---------------------------------------------------------

def _next(weekday: int) -> date:
    today = date.today()
    return today + timedelta(days=(weekday - today.weekday()) % 7 or 7)


@pytest.mark.integration
def test_admin_replaces_hours_from_a_date_and_earlier_days_are_kept(created):
    new = form(days=["mon", "tue", "wed", "thu", "fri"], ranges=[("10:00", "13:00")], start_date=date.today(), weeks=3)
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
    before = provisioning.office_blocks(doctor["id"])
    switch = _next(0) + timedelta(days=7)  # a Monday at least a week out
    change = ChangeHoursRequest(days=["tue", "thu"], ranges=[("15:00", "17:00"), ("09:00", "11:00")], start_date=switch, weeks=2)
    with SessionLocal() as db:
        preview = onboarding.preview_hours(db, admin(), doctor["id"], change)
        assert preview["problems"] == [] and preview["held_outside"] == []
        updated = onboarding.change_hours(db, admin(), doctor["id"], change)
    after = provisioning.office_blocks(doctor["id"])
    assert sorted(b for b in after if b[0] < switch) == sorted(b for b in before if b[0] < switch)
    later = sorted(b for b in after if b[0] >= switch)
    assert {b[0].weekday() for b in later} == {1, 3} and len(later) == 2 * 2 * 2
    assert {(b[1], b[2]) for b in later} == {(time(9), time(11)), (time(15), time(17))}
    assert updated["hours_until"] == max(b[0] for b in later)
    with SessionLocal() as db:
        event = db.query(AdminAuditEvent).filter(AdminAuditEvent.action == "doctor.hours_changed",
                                                 AdminAuditEvent.payload["openemr_user_id"].astext == str(doctor["id"])).one()
        assert event.payload["from"] == str(switch)


@pytest.mark.integration
def test_changing_hours_is_refused_while_a_patient_holds_a_time_it_leaves_out(created):
    from zoneinfo import ZoneInfo

    from app.models import SlotHold
    new = form(days=["mon", "tue", "wed", "thu", "fri"], ranges=[("10:00", "13:00")], weeks=3)
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
        clinic = onboarding.clinic_for(admin())
    session_id = _case_routed_to(doctor["practitioner_id"], "NEEDS_REVIEW")
    monday = _next(0)
    held_at = datetime.combine(monday, time(10, 30), clinic.timezone)
    try:
        with SessionLocal() as db:
            from app.models import PatientCase
            case_id = db.query(PatientCase.id).filter(PatientCase.session_id == session_id).scalar()
            db.add(SlotHold(case_id=case_id, practitioner_id=doctor["practitioner_id"], slot_start=held_at))
            db.commit()
            afternoons = ChangeHoursRequest(days=["mon"], ranges=[("14:00", "16:00")], start_date=monday, weeks=1)
            mornings = ChangeHoursRequest(days=["mon"], ranges=[("10:00", "12:00")], start_date=monday, weeks=1)
            stranded = onboarding.preview_hours(db, admin(), doctor["id"], afternoons)["held_outside"]
            assert [datetime.fromisoformat(t) for t in stranded] == [held_at.astimezone(ZoneInfo(str(clinic.timezone)))]
            assert onboarding.preview_hours(db, admin(), doctor["id"], mornings)["held_outside"] == []
            before = provisioning.office_blocks(doctor["id"])
            with pytest.raises(Conflict):
                onboarding.change_hours(db, admin(), doctor["id"], afternoons)
            assert sorted(provisioning.office_blocks(doctor["id"])) == sorted(before)  # nothing was written
            # Starting the new hours after the held day is fine, and so is keeping the time covered.
            onboarding.change_hours(db, admin(), doctor["id"], ChangeHoursRequest(
                days=["mon"], ranges=[("14:00", "16:00")], start_date=monday + timedelta(days=1), weeks=1))
            onboarding.change_hours(db, admin(), doctor["id"], mornings)
            for bad in (
                ChangeHoursRequest(days=["mon"], ranges=[("10:00", "12:00")], start_date=date.today() - timedelta(days=1), weeks=1),
                ChangeHoursRequest(days=[], ranges=[("10:00", "12:00")], start_date=monday, weeks=1),
                ChangeHoursRequest(days=["mon"], ranges=[("12:00", "10:00")], start_date=monday, weeks=1),
            ):
                with pytest.raises(Unprocessable):
                    onboarding.change_hours(db, admin(), doctor["id"], bad)
            with pytest.raises(NotFound):
                onboarding.change_hours(db, admin(), 1, mornings)  # not a doctor at this hospital
    finally:
        _drop_session(session_id)


# --- edit details: everything but name, NPI and username -----------------------------------

def _edit(doctor_form: NewDoctorRequest, **overrides) -> UpdateDoctorRequest:
    values = dict(title=doctor_form.title, email=doctor_form.email, phone=doctor_form.phone,
                  specialty_code=doctor_form.specialty_code, licence=doctor_form.licence)
    return UpdateDoctorRequest(**{**values, **overrides})


def _keycloak_email(username: str) -> str | None:
    _, _, user = admin_client._user_by_username(username)
    return user.get("email") if user else None


def test_name_npi_username_and_department_are_not_editable():
    with pytest.raises(ValueError):
        UpdateDoctorRequest(email="a@b.test", specialty_code="207RC0000X", npi="1234567893")
    principal = admin()
    app.dependency_overrides[authenticate] = lambda: principal
    try:
        with TestClient(app) as client:
            for field, value in (("first_name", "X"), ("last_name", "Y"), ("username", "renamed"), ("npi", "1234567893"),
                                 ("password", "Secret#2026x"), ("department_id", "pulmonology")):
                body = {"email": "a@b.test", "specialty_code": "207RC0000X", field: value}
                assert client.put(f"{BASE}/admin/doctors/1", json=body).status_code == 422, field
    finally:
        app.dependency_overrides.pop(authenticate)


@pytest.mark.integration
def test_admin_edits_details_in_both_systems_and_identity_stays(created):
    new = form(department_id="general_medicine", specialty_code="207R00000X")
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
    email = f"edited-{uuid.uuid4().hex[:8]}@example.test"
    change = _edit(new, title="Prof.", email=email, phone="+91 98765 43210", licence="MH-12345",
                   specialty_code="207Q00000X")  # another General Medicine specialty
    with SessionLocal() as db:
        updated = onboarding.update_doctor(db, admin(), doctor["id"], change)
    assert updated["department_id"] == "general_medicine" and updated["name"].startswith("Prof. ")
    assert (updated["npi"], updated["username"], updated["practitioner_id"]) == (doctor["npi"], doctor["username"], doctor["practitioner_id"])
    assert onboarding.doctor_details(admin(), doctor["id"]) == {
        "title": "Prof.", "email": email, "phone": "+91 98765 43210", "licence": "MH-12345",
        "specialty_code": "207Q00000X", "department_id": "general_medicine"}
    assert _keycloak_email(new.username) == email
    live = next(p for p in get_hms().list_practitioners() if p.id == doctor["practitioner_id"])
    assert live.department_id == "general_medicine"
    with SessionLocal() as db:
        event = db.query(AdminAuditEvent).filter(AdminAuditEvent.action == "doctor.updated",
                                                 AdminAuditEvent.payload["username"].astext == new.username).one()
        assert event.payload["changes"]["email"] == [new.email, email]
        assert set(event.payload["changes"]) == {"title", "email", "phone", "licence", "specialty_code"}


@pytest.mark.integration
def test_the_department_is_frozen(created):
    new = form()  # cardiology
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
        with pytest.raises(Unprocessable):
            onboarding.update_doctor(db, admin(), doctor["id"], _edit(new, specialty_code="207RP1001X"))  # pulmonology's
    details = onboarding.doctor_details(admin(), doctor["id"])
    assert (details["department_id"], details["specialty_code"]) == ("cardiology", new.specialty_code)


@pytest.mark.integration
def test_an_email_another_login_uses_is_refused_and_openemr_is_put_back(created):
    first, second = form(), form()
    created += [first.username, second.username]
    with SessionLocal() as db:
        onboarding.create(db, admin(), first)
        doctor = onboarding.create(db, admin(), second)
        with pytest.raises(Conflict):
            onboarding.update_doctor(db, admin(), doctor["id"], _edit(second, email=first.email, phone="+91 1"))
    assert onboarding.doctor_details(admin(), doctor["id"])["email"] == second.email
    assert onboarding.doctor_details(admin(), doctor["id"])["phone"] == second.phone
    assert _keycloak_email(second.username) == second.email


@pytest.mark.integration
def test_unknown_specialty_and_deactivated_doctors_are_refused(created):
    new = form()
    created.append(new.username)
    with SessionLocal() as db:
        doctor = onboarding.create(db, admin(), new)
        with pytest.raises(Unprocessable):
            onboarding.update_doctor(db, admin(), doctor["id"], _edit(new, specialty_code="NOT-A-CODE"))
        with pytest.raises(NotFound):
            onboarding.update_doctor(db, admin(), 1, _edit(new))
        provisioning.set_active(doctor["id"], False)
        with pytest.raises(Conflict):
            onboarding.update_doctor(db, admin(), doctor["id"], _edit(new, phone="+91 2"))
