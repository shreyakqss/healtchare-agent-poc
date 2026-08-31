"""Department / doctor / appointment selection from the hospital configuration.

Keyword matching, not a classifier: routing is an administrative decision the
clinic configures and staff may override, and a keyword table is auditable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

MATCHABLE_KINDS = {"symptom", "reason_for_visit", "history", "condition"}


class Fact(Protocol):
    kind: str
    value: str
    normalized: str  # the clinic term this wording means, "" when none applies


@dataclass
class RoutingDecision:
    department: dict[str, Any]
    doctor: dict[str, Any] | None
    appointment_type: dict[str, Any]
    matched_keywords: list[str]
    basis: str  # "rule_hint" | "keywords" | "default"

    @property
    def rationale(self) -> str:
        if self.basis == "rule_hint":
            why = "the triage rule that fired names this specialty"
        elif self.basis == "keywords":
            why = f"the patient reported: {', '.join(self.matched_keywords)}"
        else:
            why = "no specialty keywords matched, so the default department applies"
        who = f"Assigned to {self.doctor['name']}." if self.doctor else "No doctor is rostered for this department."
        return (
            f"Routed to {self.department['name']} because {why}. "
            f"Appointment type: {self.appointment_type['label']}. {who} "
            "Advisory only - staff may accept or override."
        )


def route(
    facts: Iterable[Fact],
    config: dict[str, Any],
    priority: str,
    specialty_hint: str | None = None,
) -> RoutingDecision:
    departments = config.get("departments") or []
    by_id = {d["id"]: d for d in departments}
    if not departments:
        raise ValueError("Hospital config defines no departments.")

    department = None
    matched: list[str] = []
    basis = "default"

    if specialty_hint and specialty_hint in by_id:
        department, basis = by_id[specialty_hint], "rule_hint"
    else:
        haystack = " ".join(
            f"{f.value or ''} {getattr(f, 'normalized', '') or ''}".lower()
            for f in facts
            if f.kind in MATCHABLE_KINDS
        )
        for dep_id, keywords in (config.get("specialty_map") or {}).items():
            hits = [kw for kw in keywords if kw.lower() in haystack]
            if hits and dep_id in by_id:
                department, matched, basis = by_id[dep_id], hits, "keywords"
                break

    if department is None:
        department = next((d for d in departments if d.get("default")), departments[0])

    doctors = [d for d in config.get("doctors") or [] if d.get("department_id") == department["id"]]
    doctor = doctors[0] if doctors else None

    type_id = (config.get("priority_appointment_map") or {}).get(priority, "routine_followup")
    appointment_type = next(
        (a for a in config.get("appointment_types") or [] if a["id"] == type_id),
        {"id": type_id, "label": type_id.replace("_", " ").title()},
    )
    return RoutingDecision(department, doctor, appointment_type, matched, basis)