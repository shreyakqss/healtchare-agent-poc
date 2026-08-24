from pathlib import Path

from app.integrations.hms.mock import MockHMS
from app.integrations.hms.schemas import AppointmentRequest

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "hms" / "patients.yaml"


def test_patient_lookup_and_search():
    hms = MockHMS(FIXTURE)
    assert hms.get_patient("MRN-10022").allergies == ["Penicillin V"]
    assert [p.mrn for p in hms.search_patients("priya")] == ["MRN-10022"]
    assert hms.get_patient("nope") is None


def test_slots_follow_roster_and_requests_are_drafts():
    hms = MockHMS(FIXTURE)
    slots = hms.available_slots("cardiology", limit=3)
    assert len(slots) == 3 and all(s.practitioner_id == "dr_rao" for s in slots)
    result = hms.request_appointment(AppointmentRequest(
        case_id="c", patient_mrn="MRN-10021", patient_name="Arjun", department_id="cardiology",
        practitioner_id="dr_rao", appointment_type_id="urgent_slot", priority="high", reason="follow-up",
        preferred_slot_id=slots[0].id,
    ))
    assert result.status == "requested" and result.slot.id == slots[0].id
    assert hms.available_slots("cardiology", limit=1)[0].id != slots[0].id  # taken