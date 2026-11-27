"""Doctor-to-doctor referrals (services/referral_service) over the real API.

Needs Postgres and the OpenEMR from backend/.env: the referring doctor signs with a real
OpenEMR login and the referred visit is booked on a real doctor's calendar.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import hospital_config
from app.services.hms import effective_doctors_config
from tests.helpers import (
    BASE,
    DOCTOR_CREDENTIALS,
    answer_clinical_questions,
    new_identified_session,
    patch_intake_agents,
    skip_required_attachments,
    wait_for_status,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    patch_intake_agents(monkeypatch)
    # The HMS referral record is best effort and needs a scope the test client may not have.
    monkeypatch.setattr("app.services.referral_service.get_hms", _hms_without_referrals)


def _hms_without_referrals():
    from app.integrations.hms import get_hms

    real = get_hms()

    class _HMS:
        def __getattr__(self, name):
            return getattr(real, name)

        def record_referral(self, referral):
            return "test:referral"

    return _HMS()


def _staffed_department(other_than: str) -> dict:
    config = effective_doctors_config(hospital_config.load())
    staffed = {d["department_id"] for d in config.get("doctors") or []}
    dep = next((d for d in config["departments"] if d["id"] in staffed and d["id"] != other_than), None)
    if dep is None:
        pytest.skip("Needs a second department with a doctor rostered in OpenEMR")
    return dep


def _seen_case(client) -> tuple[str, dict]:
    sid, cid = new_identified_session(client)
    skip_required_attachments(client, cid)
    answer_clinical_questions(client, sid, opening="breathless on climbing stairs for two weeks")
    return cid, wait_for_status(client, cid, "NEEDS_REVIEW")


def test_referral_books_a_linked_visit_the_patient_can_see(client):
    cid, detail = _seen_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    refer = {**DOCTOR_CREDENTIALS, "to_department_id": target["id"],
             "reason": "Exertional breathlessness, rule out a cardiac cause", "urgency": "soon"}

    # Nothing to hand over before the doctor signs their own findings.
    assert client.post(f"{BASE}/cases/{cid}/referrals", json=refer).status_code == 409
    note = client.post(f"{BASE}/cases/{cid}/consultation-notes",
                       json={**DOCTOR_CREDENTIALS, "notes": "Breathless on exertion.", "diagnosis": "Dyspnoea"})
    assert note.status_code == 201, note.text

    res = client.post(f"{BASE}/cases/{cid}/referrals", json=refer)
    assert res.status_code == 201, res.text
    made = res.json()["referrals_made"]
    assert len(made) == 1 and made[0]["to_department_id"] == target["id"]
    assert made[0]["status"] in {"booked", "awaiting_time"} and made[0]["hms_recorded"] is True
    # One open referral per department.
    assert client.post(f"{BASE}/cases/{cid}/referrals", json=refer).status_code == 409

    child_id = made[0]["case_id"]
    child = client.get(f"{BASE}/cases/{child_id}").json()
    assert child["visit_type"] == "referral" and child["status"] == "NEEDS_REVIEW"
    assert child["routing"]["department_id"] == target["id"]
    assert child["referral"]["reason"].startswith("Exertional") and child["referral"]["source_case_id"] == cid
    assert child["triage"]["priority"]  # from the clinic's rules, not the referral's "how soon"
    # The receiving doctor sees the referring doctor's signed report on their own screen.
    assert child["referral"]["source_report"]["diagnosis"] == "Dyspnoea"
    # The patient's own words came across verbatim.
    source_values = sorted(f["value"] for f in detail["facts"])
    assert sorted(f["value"] for f in child["facts"]) == source_values

    # The patient sees who referred them and the booked time - never the reason.
    visits = client.get(f"{BASE}/cases/my-visits").json()
    mine = next(v for v in visits if v["case_id"] == child_id)
    assert mine["visit_type"] == "referral" and mine["referred_by"]
    view = client.get(f"{BASE}/cases/{child_id}/patient-view").json()
    assert view["routing"] and "Exertional" not in str(view)

    # Closing the loop: the receiving doctor's signed answer shows on the referring visit.
    seen = client.post(f"{BASE}/cases/{child_id}/consultation-notes",
                       json={**DOCTOR_CREDENTIALS, "notes": "Echo normal.", "diagnosis": "Deconditioning"})
    assert seen.status_code == 201, seen.text
    back = client.get(f"{BASE}/cases/{cid}").json()["referrals_made"][0]
    assert back["status"] == "seen" and back["outcome_diagnosis"] == "Deconditioning"


def test_referral_to_an_unknown_department_is_refused(client):
    cid, _ = _seen_case(client)
    client.post(f"{BASE}/cases/{cid}/consultation-notes", json={**DOCTOR_CREDENTIALS, "notes": "Seen."})
    res = client.post(f"{BASE}/cases/{cid}/referrals",
                      json={**DOCTOR_CREDENTIALS, "to_department_id": "nope", "reason": "Second opinion"})
    assert res.status_code == 422


# --- edge cases -----------------------------------------------------------------------------

from app.db import db_session  # noqa: E402
from tests.helpers import FINALIZER_CREDENTIALS, REVIEWER_CREDENTIALS  # noqa: E402


def _signed_case(client) -> tuple[str, dict]:
    cid, detail = _seen_case(client)
    note = client.post(f"{BASE}/cases/{cid}/consultation-notes",
                       json={**DOCTOR_CREDENTIALS, "notes": "Seen.", "diagnosis": "Dyspnoea"})
    assert note.status_code == 201, note.text
    return cid, detail


def _refer(client, cid, dep_id, **extra):
    return client.post(f"{BASE}/cases/{cid}/referrals", json={
        **DOCTOR_CREDENTIALS, "to_department_id": dep_id, "reason": "Please assess", **extra})


def _audit(case_id: str) -> list[str]:
    import uuid as _uuid

    from app.models import AuditEvent
    with db_session() as db:
        return [a for (a,) in db.query(AuditEvent.action).filter(AuditEvent.case_id == _uuid.UUID(case_id)).all()]


def test_patient_can_change_the_referred_visits_time(client):
    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    child_id = _refer(client, cid, target["id"]).json()["referrals_made"][0]["case_id"]

    view = client.get(f"{BASE}/cases/{child_id}/patient-view").json()
    routing = view["routing"]
    assert routing["slot_confirmed"] is True  # booked by the referral, not just suggested
    other = next((s for s in routing["slot_options"]
                  if s["id"] != routing["selected_slot_id"] and not s.get("taken")), None)
    if other is None:
        pytest.skip("Only one free time in the department")
    res = client.post(f"{BASE}/cases/{child_id}/appointment-slot", json={"slot_id": other["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["routing"]["selected_slot_id"] == other["id"]
    # The referring doctor sees the patient's choice.
    made = client.get(f"{BASE}/cases/{cid}").json()["referrals_made"][0]
    assert made["status"] == "booked" and made["doctor_name"] == (other.get("doctor_name") or made["doctor_name"])


def test_booking_failure_keeps_the_referral_for_the_patient_to_book(client, monkeypatch):
    from app.core.errors import ServiceUnavailable

    def fail(*_a, **_k):
        raise ServiceUnavailable("calendar down")

    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    monkeypatch.setattr("app.services.referral_service.appointment_service.book", fail)
    res = _refer(client, cid, target["id"])
    assert res.status_code == 201, res.text
    made = res.json()["referrals_made"][0]
    assert made["status"] == "awaiting_time"
    assert "appointment.booking_failed" in _audit(made["case_id"])
    child = client.get(f"{BASE}/cases/{made['case_id']}/patient-view").json()
    assert child["routing"]["slot_options"]  # the patient can still pick a time


def test_hms_record_failure_never_undoes_the_referral(client, monkeypatch):
    import httpx

    class _Refusing:
        def __getattr__(self, name):
            from app.integrations.hms import get_hms
            return getattr(get_hms(), name)

        def record_referral(self, referral):
            raise httpx.HTTPError("401")

    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    monkeypatch.setattr("app.services.referral_service.get_hms", lambda: _Refusing())
    res = _refer(client, cid, target["id"])
    assert res.status_code == 201, res.text
    made = res.json()["referrals_made"][0]
    assert made["hms_recorded"] is False and made["status"] in {"booked", "awaiting_time"}
    assert "referral.hms_record_failed" in _audit(cid)


def test_rejected_visit_cannot_be_referred_and_declined_referral_releases_booking(client):
    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    child_id = _refer(client, cid, target["id"]).json()["referrals_made"][0]["case_id"]

    # The receiving doctor declines the referred visit: the booking is released.
    res = client.post(f"{BASE}/cases/{child_id}/review",
                      json={"decision": "reject", "comment": "Not cardiac", **REVIEWER_CREDENTIALS})
    assert res.status_code == 201, res.text
    made = client.get(f"{BASE}/cases/{cid}").json()["referrals_made"][0]
    assert made["status"] == "cancelled"
    assert "appointment.cancelled" in _audit(child_id)
    # A cancelled referral no longer blocks a new one to the same department.
    assert _refer(client, cid, target["id"]).status_code == 201
    # And a rejected visit cannot itself refer on.
    assert _refer(client, child_id, detail["routing"]["department_id"]).status_code == 409


def test_referred_visit_can_be_released_and_closes_the_loop(client):
    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    child_id = _refer(client, cid, target["id"]).json()["referrals_made"][0]["case_id"]
    note = client.post(f"{BASE}/cases/{child_id}/consultation-notes",
                       json={**DOCTOR_CREDENTIALS, "notes": "Echo normal.", "diagnosis": "Anxiety",
                             "follow_up_instructions": "Follow-up: as needed"})
    assert note.status_code == 201, note.text
    fin = client.post(f"{BASE}/cases/{child_id}/finalize", json=FINALIZER_CREDENTIALS)
    assert fin.status_code == 200, fin.text
    assert fin.json()["status"] == "COMPLETED"
    made = client.get(f"{BASE}/cases/{cid}").json()["referrals_made"][0]
    assert made["status"] == "completed" and made["outcome_diagnosis"] == "Anxiety"
    # The patient sees the referred visit's released summary like any other visit.
    view = client.get(f"{BASE}/cases/{child_id}/patient-view").json()
    assert view["status"] == "COMPLETED" and view["final_summary"] is not None


def test_a_completed_visit_can_still_refer(client):
    cid, detail = _signed_case(client)
    fin = client.post(f"{BASE}/cases/{cid}/finalize", json=FINALIZER_CREDENTIALS)
    assert fin.status_code == 200, fin.text
    target = _staffed_department(detail["routing"]["department_id"])
    assert _refer(client, cid, target["id"]).status_code == 201


def test_referral_context_reaches_the_receiving_doctors_agents(client):
    import uuid as _uuid

    from app.services import doctor_assistant_service

    cid, detail = _signed_case(client)
    target = _staffed_department(detail["routing"]["department_id"])
    child_id = _refer(client, cid, target["id"], question="Rule out angina?").json()["referrals_made"][0]["case_id"]
    with db_session() as db:
        text = doctor_assistant_service.case_context(db, _uuid.UUID(child_id))
    assert "REFERRAL from" in text and "Rule out angina?" in text
    assert "Diagnosis: Dyspnoea" in text  # the referring doctor's signed report
    assert "Intake conversation" in text  # the referring visit's intake, linked
