"""Map patient-reported text to a hospital department.

Keyword matching against the `specialty_map` in hospital.yaml. Deliberately
not a classifier: routing is an administrative decision the clinic configures
and staff can override, and a keyword table is auditable in a way a model
output is not.
"""
from typing import Any, Iterable, Protocol
from services import hospital_config

MATCHABLE_KINDS = {"symptom", "reason_for_visit", "history", "condition"}


class Fact(Protocol):
    kind: str
    value: str


def match_department(
    facts: Iterable[Fact], specialty_hint: str | None = None
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (department, matched_keywords).

    A `specialty_hint` from a triage rule wins — the rule engine is
    authoritative, and its hint is part of the approved configuration.
    Otherwise the first department whose keywords appear in the facts wins.
    """
    if specialty_hint:
        department = hospital_config.department_by_id(specialty_hint)
        if department:
            return department, [f"triage rule hint: {specialty_hint}"]

    haystack = " ".join(
        (f.value or "").lower() for f in facts if f.kind in MATCHABLE_KINDS
    )

    for department_id, keywords in hospital_config.specialty_map().items():
        hits = [kw for kw in keywords if kw.lower() in haystack]
        if hits:
            department = hospital_config.department_by_id(department_id)
            if department:
                return department, hits

    return hospital_config.default_department(), []

def pick_doctor(department_id: str) -> dict[str, Any] | None:
    """First doctor listed for the department.

    ponytail: no availability check — the POC has no calendar. Swap in a real
    scheduler lookup here when working_days/appointments become real.
    """
    roster = hospital_config.doctors_for_department(department_id)
    return roster[0] if roster else None
