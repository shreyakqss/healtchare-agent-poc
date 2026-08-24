"""Rule-based administrative triage.

The *only* thing allowed to decide a priority. No LLM, no DB, no I/O. Agents
call `evaluate()` and persist what it returns; they never adjust it.
Inputs are duck-typed so SQLAlchemy rows and plain test objects both work.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

_UNIT_DAYS = {"hour": 1 / 24, "day": 1, "week": 7, "fortnight": 14, "month": 30, "year": 365}
_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hour|day|week|fortnight|month|year)s?", re.I)
_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple": 2, "few": 3, "several": 3,
}
_WORD_RE = re.compile(
    r"\b(" + "|".join(_WORDS) + r")\s+(?:of\s+)?(hour|day|week|fortnight|month|year)s?", re.I
)

SYMPTOM_KINDS = {"symptom", "reason_for_visit"}
HISTORY_KINDS = {"history", "condition"}
DURATION_KINDS = {"duration"}


class Fact(Protocol):
    kind: str
    value: str


class Entry(Protocol):
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
    """'3 weeks' -> 21, 'a month' -> 30, unrecognised -> None (never fires a rule)."""
    if m := _NUMERIC_RE.search(text):
        return float(m.group(1)) * _UNIT_DAYS[m.group(2).lower()]
    if m := _WORD_RE.search(text):
        return _WORDS[m.group(1).lower()] * _UNIT_DAYS[m.group(2).lower()]
    return None


def find_allergy_conflicts(entries: Iterable[Entry]) -> list[dict[str, Any]]:
    """Name overlap between reported allergies and reported medications.

    A flag for a human, not a pharmacological interaction check.
    """
    items = list(entries)
    allergies = [e for e in items if e.kind == "allergy" and (e.name or "").strip()]
    meds = [e for e in items if e.kind == "medication" and (e.name or "").strip()]
    conflicts = []
    for a in allergies:
        al = a.name.strip().lower()
        for m in meds:
            ml = m.name.strip().lower()
            if al in ml or ml in al:
                conflicts.append(
                    {
                        "type": "allergy_medication_conflict",
                        "allergy": a.name,
                        "medication": m.name,
                        "message": (
                            f"Reported allergy '{a.name}' overlaps with reported medication "
                            f"'{m.name}'. Requires clinician review."
                        ),
                    }
                )
    return conflicts


def _hits(facts: list[Fact], kinds: set[str], keywords: list[str]):
    for f in facts:
        if f.kind not in kinds:
            continue
        value = (f.value or "").lower()
        for kw in keywords:
            if kw.lower() in value:
                yield kw, f


def _evidence(matched_on: str, hits) -> list[dict[str, Any]]:
    return [{"matched_on": matched_on, "keyword": kw, "text": f.value, "fact_kind": f.kind} for kw, f in hits]


def _match(condition: dict[str, Any], facts: list[Fact], conflicts: list[dict[str, Any]]):
    """Return (matched, evidence). An empty condition always matches."""
    evidence: list[dict[str, Any]] = []
    if not condition:
        return True, evidence

    if kws := condition.get("any_symptom"):
        hits = list(_hits(facts, SYMPTOM_KINDS, kws))
        if not hits:
            return False, []
        evidence += _evidence("symptom", hits)

    if kws := condition.get("all_symptoms"):
        hits = list(_hits(facts, SYMPTOM_KINDS, kws))
        if {kw for kw, _ in hits} != set(kws):
            return False, []
        evidence += _evidence("symptom", hits)

    if kws := condition.get("any_history"):
        hits = list(_hits(facts, HISTORY_KINDS, kws))
        if not hits:
            return False, []
        evidence += _evidence("history", hits)

    if (threshold := condition.get("min_duration_days")) is not None:
        qualifying = [
            (d, f) for f in facts if f.kind in DURATION_KINDS
            if (d := parse_duration_days(f.value)) is not None and d >= threshold
        ]
        if not qualifying:
            return False, []
        evidence += [
            {"matched_on": "duration", "days": d, "threshold_days": threshold, "text": f.value, "fact_kind": f.kind}
            for d, f in qualifying
        ]

    if condition.get("allergy_conflict"):
        if not conflicts:
            return False, []
        evidence += [{"matched_on": "allergy_conflict", "text": c["message"], "fact_kind": "allergy_medication"} for c in conflicts]

    return True, evidence


def evaluate(facts: Iterable[Fact], entries: Iterable[Entry], rules: Iterable[Rule]) -> TriageOutcome:
    """High -> medium -> low, first match wins. A rule with an empty condition is the fallback."""
    facts = list(facts)
    conflicts = find_allergy_conflicts(entries)

    for rule in sorted(rules, key=lambda r: (PRIORITY_RANK.get(r.priority, 99), r.code)):
        matched, evidence = _match(rule.condition or {}, facts, conflicts)
        if not matched:
            continue
        if not evidence:
            evidence = [{"matched_on": "default", "text": rule.explanation, "fact_kind": "none"}]
        return TriageOutcome(
            priority=rule.priority,
            rule_ids=[str(getattr(rule, "id", rule.code))],
            rule_codes=[rule.code],
            warnings=conflicts,
            evidence=[{"rule_code": rule.code, **e} for e in evidence],
            specialty_hint=getattr(rule, "specialty_hint", None),
        )

    raise ValueError("No triage rule matched and no fallback rule is configured.")