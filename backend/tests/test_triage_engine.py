from dataclasses import dataclass, field

import pytest

from app.domain import triage_engine as engine


@dataclass
class F:
    kind: str
    value: str
    normalized: str = ""


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
    emergency: bool = False


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


def test_paraphrase_matches_through_the_clinic_term():
    out = engine.evaluate([F("symptom", "a crushing weight on my ribs", "chest pain")], [], RULES)
    assert out.priority == "high"
    assert out.rule_codes == ["TR-HIGH-001"]
    # The evidence still quotes what the patient actually said.
    assert out.evidence[0]["text"] == "a crushing weight on my ribs"


def test_paraphrase_without_a_clinic_term_stays_routine():
    out = engine.evaluate([F("symptom", "a crushing weight on my ribs")], [], RULES)
    assert out.priority == "low"

RED_FLAG = R("TR-EMERG-001", "high", {"any_symptom": ["chest pain"], "any_severity": ["severe", "sever", "immense"]}, emergency=True)


def test_severe_chest_pain_is_a_red_flag():
    """The live case: the severity came in the duration answer, not the symptom."""
    facts = [F("reason_for_visit", "chest pain and nausea"), F("duration", "2 days its sever and im feeling immese pain")]
    out = engine.evaluate(facts, [], [*RULES, RED_FLAG])
    assert out.emergency and out.rule_codes == ["TR-EMERG-001"]
    assert any(e["matched_on"] == "severity" for e in out.evidence)


def test_chest_pain_without_severity_is_urgent_not_emergency():
    out = engine.evaluate([F("symptom", "chest pain"), F("duration", "several days")], [], [*RULES, RED_FLAG])
    assert out.priority == "high" and not out.emergency
    assert out.rule_codes == ["TR-HIGH-001"]
