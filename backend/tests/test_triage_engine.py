"""The one Phase 1 test: the rule engine must not silently break.

Everything else in the POC is demo scaffolding. This is the piece that decides
how urgently a patient is seen, so it gets a check that fails loudly.

Run from backend/:  pytest tests/
"""

from dataclasses import dataclass

import pytest

from agents import question_planner, urgency_evaluator
from services import hospital_config, triage_engine


@dataclass
class F:
    kind: str
    value: str


@dataclass
class A:
    kind: str
    name: str


@dataclass
class R:
    code: str
    priority: str
    condition: dict
    explanation: str = "because the rule says so"
    action: str = "do the thing"
    specialty_hint: str | None = None


def load_configured_rules() -> list[R]:
    """Use the active hospital's real config so the test fails if it drifts."""
    config = hospital_config.load()
    return [
        R(
            code=r["code"],
            priority=r["priority"],
            condition=r.get("condition") or {},
            explanation=r["explanation"],
            action=r["action"],
            specialty_hint=r.get("specialty_hint"),
        )
        for r in config["triage_rules"]["rules"]
    ]


RULES = load_configured_rules()


# --- every tier is reachable from the shipped config -----------------------


def test_high_priority_fires_on_escalation_symptom():
    outcome = triage_engine.evaluate(
        [F("symptom", "I have had chest pain since this morning")], [], RULES
    )
    assert outcome.priority == "high"
    assert "TR-HIGH-001" in outcome.rule_codes


def test_medium_priority_fires_on_long_duration():
    outcome = triage_engine.evaluate(
        [F("symptom", "mild headache"), F("duration", "about 3 weeks")], [], RULES
    )
    assert outcome.priority == "medium"
    assert "TR-MED-001" in outcome.rule_codes


def test_low_priority_is_the_fallback():
    outcome = triage_engine.evaluate(
        [F("symptom", "mild headache"), F("duration", "2 days")], [], RULES
    )
    assert outcome.priority == "low"
    assert "TR-LOW-000" in outcome.rule_codes


# --- the non-negotiables ---------------------------------------------------


def test_every_outcome_carries_a_rule_and_evidence():
    """The foundation doc requires each priority to trace to a rule + evidence."""
    cases = [
        [F("symptom", "chest pain")],
        [F("symptom", "cough"), F("duration", "one month")],
        [F("symptom", "mild rash")],
        [],
    ]
    for facts in cases:
        outcome = triage_engine.evaluate(facts, [], RULES)
        assert outcome.rule_ids, f"no rule id for {facts}"
        assert outcome.rule_codes, f"no rule code for {facts}"
        assert outcome.evidence, f"no evidence for {facts}"
        assert all("rule_code" in item for item in outcome.evidence)


def test_allergy_medication_conflict_raises_a_warning():
    outcome = triage_engine.evaluate(
        [F("symptom", "mild headache")],
        [A("allergy", "Penicillin"), A("medication", "Penicillin V 250mg")],
        RULES,
    )
    assert outcome.warnings, "an allergy/medication overlap must warn"
    assert outcome.warnings[0]["type"] == "allergy_medication_conflict"
    assert outcome.priority == "high"
    assert "TR-HIGH-002" in outcome.rule_codes


def test_placeholder_answers_cannot_conflict_with_each_other():
    """A patient who answered both questions unusably is not an escalation.

    Intake closes a field it could not extract by writing the same sentence
    into the row — so an allergy row and a medication row can both read
    "Answered - see the intake transcript". The conflict check is a name
    overlap, and that sentence overlaps itself: left in, it escalated cases to
    high priority on a conflict between two placeholders. The filter runs
    before the engine, so the rows still stand in the record.
    """
    entries = [
        A("allergy", question_planner.NOT_CAPTURED),
        A("medication", question_planner.NOT_CAPTURED),
    ]
    assert triage_engine.evaluate([F("symptom", "mild headache")], entries, RULES).priority == "high"

    kept = urgency_evaluator.clinical_entries(entries)
    assert kept == []
    outcome = triage_engine.evaluate([F("symptom", "mild headache")], kept, RULES)
    assert outcome.warnings == []
    assert outcome.priority == "low"


def test_a_real_allergy_survives_the_placeholder_filter():
    entries = [
        A("allergy", "Penicillin"),
        A("medication", question_planner.NONE_REPORTED),
    ]
    assert [entry.name for entry in urgency_evaluator.clinical_entries(entries)] == [
        "Penicillin"
    ]


def test_unrelated_medication_does_not_warn():
    outcome = triage_engine.evaluate(
        [F("symptom", "mild headache")],
        [A("allergy", "Penicillin"), A("medication", "Metformin 500mg")],
        RULES,
    )
    assert outcome.warnings == []


def test_attachment_context_cannot_change_priority():
    """Uploads are stored and displayed only — they never drive a priority.

    The engine's signature takes facts, allergies and rules; extracted document
    text is not among them. This pins that: adding attachment-derived text as a
    fact kind the rules don't read leaves the outcome untouched.
    """
    baseline = triage_engine.evaluate([F("symptom", "mild rash")], [], RULES)
    with_attachment = triage_engine.evaluate(
        [
            F("symptom", "mild rash"),
            F("attachment_text", "RADIOLOGY REPORT: chest pain, severe bleeding"),
        ],
        [],
        RULES,
    )
    assert with_attachment.priority == baseline.priority == "low"
    assert with_attachment.rule_codes == baseline.rule_codes


# --- duration parsing is the one bit of real logic -------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3 weeks", 21),
        ("2 days", 2),
        ("a month", 30),
        ("about 6 hours", 0.25),
        ("couple of weeks", 14),
        ("since forever", None),
        ("", None),
    ],
)
def test_parse_duration_days(text, expected):
    assert triage_engine.parse_duration_days(text) == expected


def test_unparseable_duration_cannot_fire_a_duration_rule():
    outcome = triage_engine.evaluate(
        [F("symptom", "mild headache"), F("duration", "ages")], [], RULES
    )
    assert outcome.priority == "low"


def test_missing_fallback_rule_raises_rather_than_guessing():
    high_only = [r for r in RULES if r.priority == "high"]
    with pytest.raises(ValueError, match="fallback"):
        triage_engine.evaluate([F("symptom", "mild headache")], [], high_only)
