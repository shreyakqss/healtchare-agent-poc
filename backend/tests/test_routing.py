from dataclasses import dataclass

from app.domain.routing import by_earliest, doctor_choice, least_loaded, one_per_time, route, with_doctor

CONFIG = {
    "departments": [{"id": "general", "name": "General", "default": True}, {"id": "cardio", "name": "Cardiology"}],
    "doctors": [{"id": "d1", "name": "Dr One", "department_id": "cardio"}],
    "specialty_map": {"cardio": ["chest pain", "palpitations"]},
    "appointment_types": [{"id": "urgent_slot", "label": "Urgent"}, {"id": "routine_followup", "label": "Routine"}],
    "priority_appointment_map": {"high": "urgent_slot", "low": "routine_followup"},
}


@dataclass
class F:
    kind: str
    value: str
    normalized: str = ""


def test_rule_hint_beats_keywords():
    d = route([F("symptom", "headache")], CONFIG, "high", specialty_hint="cardio")
    assert d.department["id"] == "cardio" and d.basis == "rule_hint" and d.doctor["id"] == "d1"
    assert d.appointment_type["id"] == "urgent_slot"


def test_keyword_match():
    d = route([F("reason_for_visit", "Palpitations at night")], CONFIG, "low")
    assert d.department["id"] == "cardio" and d.matched_keywords == ["palpitations"]


def test_clinic_term_routes_a_paraphrase():
    d = route([F("symptom", "my heart keeps fluttering", "palpitations")], CONFIG, "low")
    assert d.department["id"] == "cardio" and d.matched_keywords == ["palpitations"]


def test_default_department_without_doctor():
    d = route([F("symptom", "sore toe")], CONFIG, "low")
    assert d.department["id"] == "general" and d.doctor is None and d.basis == "default"
    assert "default department" in d.rationale

def test_route_offers_every_doctor_in_the_department():
    config = {**CONFIG, "doctors": [*CONFIG["doctors"], {"id": "d2", "name": "Dr Two", "department_id": "cardio"}]}
    d = route([F("symptom", "chest pain")], config, "low")
    assert [doc["id"] for doc in d.doctors] == ["d1", "d2"]


def _slot(pid: str, hour: int, taken: bool = False) -> dict:
    return {"id": f"{pid}-{hour}", "practitioner_id": pid, "start": f"2030-01-07T{hour:02d}:00:00+00:00", "taken": taken}


def test_earliest_time_wins_and_fewer_open_cases_breaks_a_tie():
    slots = [_slot("busy", 10), _slot("busy", 9), _slot("idle", 10)]
    ordered = by_earliest(slots, {"busy": 3})
    assert [s["id"] for s in ordered] == ["busy-9", "idle-10", "busy-10"]  # earliest beats load


def test_any_doctor_view_keeps_one_time_each_preferring_the_cases_own_then_a_free_one():
    slots = [_slot("a", 9, taken=True), _slot("b", 9), _slot("a", 10), _slot("b", 10), _slot("a", 11, taken=True)]
    assert [s["id"] for s in one_per_time(slots, keep_id="b-10")] == ["b-9", "b-10", "a-11"]


def test_with_no_free_time_the_least_loaded_doctor_is_assigned():
    doctors = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert least_loaded(doctors, {"a": 2, "b": 1, "c": 1})["id"] == "b"
    assert least_loaded([], {}) is None


def test_urgent_patients_get_no_doctor_choice():
    assert not doctor_choice("high")
    assert doctor_choice("medium") and doctor_choice("low") and doctor_choice(None)


def test_rationale_names_how_the_doctor_was_assigned_and_survives_a_name_with_a_period():
    config = {**CONFIG, "doctors": [{"id": "d1", "name": "Dr. One", "department_id": "cardio"},
                                    {"id": "d2", "name": "Dr. Two", "department_id": "cardio"}]}
    d = route([F("symptom", "chest pain")], config, "low")
    d.doctor, d.assigned_by = d.doctors[1], "earliest"
    assert d.rationale.endswith("Assigned to Dr. Two (earliest free time among the department's 2 doctors).")
    changed = with_doctor(d.rationale, "Dr. One", "the patient's choice")
    assert changed.endswith("Advisory only - staff may accept or override. Assigned to Dr. One (the patient's choice).")
    assert changed.count("Assigned to") == 1



def test_red_flag_routes_by_keyword_and_gives_no_doctor_choice():
    facts = [type("F", (), {"kind": "symptom", "value": "severe chest pain", "normalized": ""})()]
    assert route(facts, CONFIG, "high").department["id"] == "cardio"
    assert not doctor_choice("low", emergency=True)
