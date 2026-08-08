"""Rule-based administrative triage.

This module is the *only* thing allowed to decide a priority. It runs no LLM
calls, touches no database session, and performs no I/O — which is exactly what
makes it testable and what stops a language model from ever talking its way
past a safety rule. Agents call `evaluate()` and persist what it returns; they
do not adjust it.

Inputs are duck-typed on purpose: SQLAlchemy models satisfy them, and so do
plain objects in tests.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

_DURATION_UNIT_DAYS = {
    "hour": 1 / 24,
    "day": 1,
    "week": 7,
    "fortnight": 14,
    "month": 30,
    "year": 365,
}
_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(hour|day|week|fortnight|month|year)s?", re.IGNORECASE
)
_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple": 2,
    "few": 3, "several": 3,
}
_WORD_DURATION_RE = re.compile(
    r"\b(" + "|".join(_WORD_NUMBERS) + r")\s+(?:of\s+)?"
    r"(hour|day|week|fortnight|month|year)s?",
    re.IGNORECASE,
)

SYMPTOM_KINDS = {"symptom", "reason_for_visit"}
HISTORY_KINDS = {"history", "condition"}
DURATION_KINDS = {"duration"}


class Fact(Protocol):
    kind: str
    value: str
class Allergy(Protocol):
    kind: str  # allergy | medication
    name: str
class Rule(Protocol):
    code: str
    priority: str
    condition: dict[str, Any]
    explanation: str
    action: str


@dataclass
class TriageOutcome:
    priority: str
    rule_ids: list[str] = field(default_factory=list)
    rule_codes: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    specialty_hint: str | None = None


def parse_duration_days(text: str) -> float | None:
    """Best-effort duration in days from free text like '3 weeks' or 'a month'.

    ponytail: regex over two phrasings, not an NLP date parser. Returns None on
    anything unrecognised so an unparsed duration can never fire a rule.
    """
    match = _DURATION_RE.search(text)
    if match:
        return float(match.group(1)) * _DURATION_UNIT_DAYS[match.group(2).lower()]

    match = _WORD_DURATION_RE.search(text)
    if match:
        count = _WORD_NUMBERS[match.group(1).lower()]
        return count * _DURATION_UNIT_DAYS[match.group(2).lower()]

    return None

def find_allergy_conflicts(
    allergies_and_meds: Iterable[Allergy],
) -> list[dict[str, Any]]:
    """Report reported allergies that also appear in the reported medication list.

    Deliberately a name-overlap check, not a pharmacological interaction
    database — this flags the case for a human, it does not assess it.
    """
    items = list(allergies_and_meds)
    allergies = [a for a in items if a.kind == "allergy"]
    medications = [m for m in items if m.kind == "medication"]

    conflicts: list[dict[str, Any]] = []
    for allergy in allergies:
        allergen = (allergy.name or "").strip().lower()
        if not allergen:
            continue
        for medication in medications:
            med = (medication.name or "").strip().lower()
            if not med:
                continue
            if allergen in med or med in allergen:
                conflicts.append(
                    {
                        "type": "allergy_medication_conflict",
                        "allergy": allergy.name,
                        "medication": medication.name,
                        "message": (
                            f"Reported allergy '{allergy.name}' overlaps with reported "
                            f"medication '{medication.name}'. Requires clinician review."
                        ),
                    }
                )
    return conflicts

def _matching_facts(facts: Iterable[Fact], kinds: set[str], keywords: list[str]):
    """Yield (keyword, fact) for every keyword found in a fact of the given kinds."""
    for fact in facts:
        if fact.kind not in kinds:
            continue
        value = (fact.value or "").lower()
        for keyword in keywords:
            if keyword.lower() in value:
                yield keyword, fact

def _evaluate_condition(
    condition: dict[str, Any],
    facts: list[Fact],
    conflicts: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    """Return (matched, evidence). An empty condition always matches."""
    evidence: list[dict[str, Any]] = []

    if not condition:
        return True, evidence

    if keywords := condition.get("any_symptom"):
        hits = list(_matching_facts(facts, SYMPTOM_KINDS, keywords))
        if not hits:
            return False, []
        evidence += [
            {"matched_on": "symptom", "keyword": kw, "text": f.value, "fact_kind": f.kind}
            for kw, f in hits
        ]

    if keywords := condition.get("all_symptoms"):
        hits = list(_matching_facts(facts, SYMPTOM_KINDS, keywords))
        if {kw for kw, _ in hits} != set(keywords):
            return False, []
        evidence += [
            {"matched_on": "symptom", "keyword": kw, "text": f.value, "fact_kind": f.kind}
            for kw, f in hits
        ]

    if keywords := condition.get("any_history"):
        hits = list(_matching_facts(facts, HISTORY_KINDS, keywords))
        if not hits:
            return False, []
        evidence += [
            {"matched_on": "history", "keyword": kw, "text": f.value, "fact_kind": f.kind}
            for kw, f in hits
        ]

    if (threshold := condition.get("min_duration_days")) is not None:
        durations = [
            (parse_duration_days(f.value), f)
            for f in facts
            if f.kind in DURATION_KINDS
        ]
        qualifying = [(d, f) for d, f in durations if d is not None and d >= threshold]
        if not qualifying:
            return False, []
        evidence += [
            {
                "matched_on": "duration",
                "days": days,
                "threshold_days": threshold,
                "text": f.value,
                "fact_kind": f.kind,
            }
            for days, f in qualifying
        ]

    if condition.get("allergy_conflict"):
        if not conflicts:
            return False, []
        evidence += [
            {
                "matched_on": "allergy_conflict",
                "text": c["message"],
                "fact_kind": "allergy_medication",
            }
            for c in conflicts
        ]

    return True, evidence

def evaluate(
    facts: Iterable[Fact],
    allergies_and_meds: Iterable[Allergy],
    rules: Iterable[Rule],
) -> TriageOutcome:
    """Evaluate approved rules against patient-reported facts.

    Rules are considered high -> medium -> low; the first match wins. A rule
    with an empty condition is the guaranteed fallback, so every outcome carries
    at least one rule and one evidence item.
    """
    facts = list(facts)
    conflicts = find_allergy_conflicts(allergies_and_meds)

    ordered = sorted(
        rules, key=lambda r: (PRIORITY_RANK.get(r.priority, 99), r.code)
    )

    for rule in ordered:
        matched, evidence = _evaluate_condition(rule.condition or {}, facts, conflicts)
        if not matched:
            continue

        if not evidence:
            # The fallback rule matches on the absence of anything else, so give
            # the clinician something concrete rather than an empty panel.
            evidence = [
                {
                    "matched_on": "default",
                    "text": rule.explanation,
                    "fact_kind": "none",
                }
            ]

        return TriageOutcome(
            priority=rule.priority,
            rule_ids=[str(getattr(rule, "id", rule.code))],
            rule_codes=[rule.code],
            warnings=conflicts,
            evidence=[{"rule_code": rule.code, **item} for item in evidence],
            specialty_hint=getattr(rule, "specialty_hint", None),
        )

    # Only reachable if the hospital config has no fallback rule. Fail toward
    # human review rather than silently assigning a priority of our own.
    raise ValueError(
        "No triage rule matched and no fallback rule is configured. "
        "Add a rule with an empty condition to hospital.yaml."
    )
