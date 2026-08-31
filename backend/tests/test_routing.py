from dataclasses import dataclass

from app.domain.routing import route

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