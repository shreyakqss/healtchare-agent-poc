from dataclasses import dataclass, field

import pytest

from app.domain import triage_engine as engine


@dataclass
class F:
    kind: str
    value: str


@dataclass
class E:
    kind: str
    name: str


@dataclass
class R:
    code: str
    priority: str
    condition: dict = field(default_factory=dict)
    explanation: str = "why"
    action: str = "do"
    specialty_hint: str | None = None
    id: str = "id"


RULES = [
    R("TR-HIGH-001", "high", {"any_symptom": ["chest pain"]}, specialty_hint="cardiology"),
    R("TR-HIGH-002", "high", {"allergy_conflict": True}),
    R("TR-MED-001", "medium", {"min_duration_days": 14}),
    R("TR-MED-002", "medium", {"any_symptom": ["fever"], "any_history": ["diabetes"]}),
    R("TR-LOW-000", "low", {}),
]


def test_high_symptom_wins_and_carries_hint():
    out = engine.evaluate([F("symptom", "sharp chest pain")], [], RULES)
    assert out.priority == "high"
    assert out.rule_codes == ["TR-HIGH-001"]
    assert out.specialty_hint == "cardiology"
    assert out.evidence[0]["matched_on"] == "symptom"


def test_duration_threshold_medium():
    out = engine.evaluate([F("symptom", "cough"), F("duration", "about three weeks")], [], RULES)
    assert out.priority == "medium"
    assert out.rule_codes == ["TR-MED-001"]


def test_symptom_plus_history_medium():
    out = engine.evaluate([F("symptom", "fever"), F("history", "type 2 diabetes")], [], RULES)
    assert out.rule_codes == ["TR-MED-002"]


def test_allergy_conflict_escalates_with_warning():
    out = engine.evaluate([F("symptom", "rash")], [E("allergy", "amoxicillin"), E("medication", "Amoxicillin 500mg")], RULES)
    assert out.priority == "high"
    assert out.rule_codes == ["TR-HIGH-002"]
    assert out.warnings and out.warnings[0]["type"] == "allergy_medication_conflict"


def test_fallback_always_has_evidence():
    out = engine.evaluate([F("symptom", "mild itch")], [], RULES)
    assert out.priority == "low"
    assert out.evidence[0]["matched_on"] == "default"


def test_no_fallback_raises():
    with pytest.raises(ValueError):
        engine.evaluate([], [], RULES[:-1])


@pytest.mark.parametrize("text,days", [("3 weeks", 21), ("a month", 30), ("couple of days", 2), ("since this morning", None), ("2.5 days", 2.5)])
def test_parse_duration(text, days):
    assert engine.parse_duration_days(text) == days