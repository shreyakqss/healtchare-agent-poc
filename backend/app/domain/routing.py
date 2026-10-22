"""Department / doctor / appointment selection from the hospital configuration.

Keyword matching, not a classifier: routing is an administrative decision the
clinic configures and staff may override, and a keyword table is auditable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

MATCHABLE_KINDS = {"symptom", "reason_for_visit", "history", "condition"}

# Urgency decides how soon a patient is seen, never which doctor: doctors in one department are
# equally able to see its cases. At these priorities the patient is offered the department's
# earliest times only, with no doctor to pick, so a preference can never delay them.
NO_DOCTOR_CHOICE = {"high"}
ASSIGNED_TO = " Assigned to "


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
    doctors: list[dict[str, Any]] = field(default_factory=list)  # everyone rostered in the department
    assigned_by: str = "first"  # "earliest" | "fewest_open" | "first"

    @property
    def rationale(self) -> str:
        if self.basis == "rule_hint":
            why = "the triage rule that fired names this specialty"
        elif self.basis == "keywords":
            why = f"the patient reported: {', '.join(self.matched_keywords)}"
        else:
            why = "no specialty keywords matched, so the default department applies"
        base = (
            f"Routed to {self.department['name']} because {why}. "
            f"Appointment type: {self.appointment_type['label']}. "
            "Advisory only - staff may accept or override."
        )
        if not self.doctor:
            return f"{base} No doctor is rostered for this department."
        if self.assigned_by == "earliest" and len(self.doctors) > 1:
            how = f"earliest free time among the department's {len(self.doctors)} doctors"
        elif self.assigned_by == "fewest_open" and len(self.doctors) > 1:
            how = "no free time to go by, so the doctor with the fewest open cases"
        else:
            how = ""
        return with_doctor(base, self.doctor["name"], how)


def with_doctor(rationale: str, name: str, how: str = "") -> str:
    """`rationale` with its closing "Assigned to ..." sentence (if any) replaced."""
    base = rationale.partition(ASSIGNED_TO)[0] if ASSIGNED_TO in rationale else rationale
    return f"{base}{ASSIGNED_TO}{name}" + (f" ({how})." if how else ".")


def doctor_choice(priority: str | None, emergency: bool = False) -> bool:
    """Whether the patient may pick which of the department's doctors they see."""
    return not emergency and priority not in NO_DOCTOR_CHOICE


def _start(slot: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(slot["start"]))


def by_earliest(slots: list[dict[str, Any]], open_cases: dict[str, int]) -> list[dict[str, Any]]:
    """Earliest first; at the same time, the doctor with fewer open cases first. Stable, so
    doctors tied on both keep roster order."""
    return sorted(slots, key=lambda s: (_start(s), open_cases.get(s.get("practitioner_id") or "", 0)))


def one_per_time(slots: list[dict[str, Any]], keep_id: str | None = None) -> list[dict[str, Any]]:
    """The "any doctor" view of `by_earliest`-ordered slots: one per start time - the case's own
    if it is at that time, else the first free one, else (all taken) the first, shown greyed."""
    groups: dict[datetime, list[dict[str, Any]]] = {}
    for slot in slots:
        groups.setdefault(_start(slot), []).append(slot)
    return [
        next((s for s in group if s.get("id") == keep_id), None)
        or next((s for s in group if not s.get("taken")), group[0])
        for group in groups.values()
    ]


def least_loaded(doctors: list[dict[str, Any]], open_cases: dict[str, int]) -> dict[str, Any] | None:
    """With no free time to go by: the doctor with the fewest open cases, roster order on a tie."""
    return min(doctors, key=lambda d: open_cases.get(d["id"], 0)) if doctors else None


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
    # A placeholder until the caller, which can see calendars and case loads, assigns the
    # doctor with the earliest free time (see workflows/prescreen.navigate_care).
    doctor = doctors[0] if doctors else None

    type_id = (config.get("priority_appointment_map") or {}).get(priority, "routine_followup")
    appointment_type = next(
        (a for a in config.get("appointment_types") or [] if a["id"] == type_id),
        {"id": type_id, "label": type_id.replace("_", " ").title()},
    )
    return RoutingDecision(department, doctor, appointment_type, matched, basis, doctors)