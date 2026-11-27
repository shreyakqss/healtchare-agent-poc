"""Department / doctor / appointment selection from the hospital configuration.

Keyword matching, not a classifier: routing is an administrative decision the
clinic configures and staff may override, and a keyword table is auditable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

# Only the current complaint routes a visit: a past condition ("asthma") must not pull a knee-pain
# visit to Pulmonology. Denied symptoms (`negative`) never match.
ROUTING_KINDS = {"symptom", "reason_for_visit"}


def _text(facts: list[Fact], kinds: set[str]) -> str:
    return " ".join(
        f"{f.value or ''} {getattr(f, 'normalized', '') or ''}".lower() for f in facts if f.kind in kinds
    )


def _mentions(text: str, term: str) -> bool:
    """Whole words only ("heart" is not in "heartburn", "rash" not in "crash"); a plural counts."""
    return re.search(rf"\b{re.escape(term.lower())}(?:e?s)?\b", text) is not None

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
    basis: str  # "follow_up" | "rule_hint" | "keywords" | "infection" | "default"
    doctors: list[dict[str, Any]] = field(default_factory=list)  # everyone rostered in the department
    assigned_by: str = "first"  # "previous_doctor" | "earliest" | "fewest_open" | "first"
    # The AI router's part (see accept_ai_pick): "" when it was not asked (follow-up, rule hint).
    ai_status: str = ""  # "used" | "protected" | "invalid" | "unavailable"
    ai_reason: str = ""
    rules_department: str = ""  # what the keyword rules chose, when the AI's pick was used instead

    @property
    def rationale(self) -> str:
        if self.basis == "ai":
            note = f" Clinic keyword rules suggested {self.rules_department}." if self.rules_department else ""
            base = (
                f"Routed to {self.department['name']} by the AI router: {self.ai_reason.rstrip('.')}.{note} "
                f"Appointment type: {self.appointment_type['label']}. Advisory only - staff may accept or override."
            )
            return self._with_assignment(base)
        if self.basis == "follow_up":
            why = "this is a follow-up of the patient's earlier visit there"
        elif self.basis == "rule_hint":
            why = "the triage rule that fired names this specialty"
        elif self.basis == "keywords":
            why = f"the patient reported: {', '.join(self.matched_keywords)}"
        elif self.basis == "infection":
            why = f"{', '.join(self.matched_keywords)} together point to an infection, which this department sees first"
        else:
            why = "no specialty keywords matched, so the default department applies"
        ai_note = {
            "protected": " The AI router suggested otherwise; the clinic keeps heart symptoms without fever here.",
            "invalid": " The AI router's answer failed the clinic's checks, so the keyword rules decided.",
            "unavailable": " The AI router was unavailable, so the keyword rules decided.",
        }.get(self.ai_status, "")
        base = (
            f"Routed to {self.department['name']} because {why}.{ai_note} "
            f"Appointment type: {self.appointment_type['label']}. "
            "Advisory only - staff may accept or override."
        )
        return self._with_assignment(base)

    def _with_assignment(self, base: str) -> str:
        if not self.doctor:
            return f"{base} No doctor is rostered for this department."
        if self.assigned_by == "previous_doctor":
            how = "saw the patient at the visit this follows up"
        elif self.assigned_by == "earliest" and len(self.doctors) > 1:
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


def accept_ai_pick(
    rules: RoutingDecision, pick_id: str, facts_used: list[str], facts: Iterable[Fact], config: dict[str, Any],
) -> str:
    """Whether the AI router's department is used ("used") or the keyword rules stand
    ("protected" / "invalid"). The AI may only name a configured department and must rest on
    facts the case really has; and a department listed in `ai_routing.protected` (Cardiology)
    keeps a case its keywords sent there unless an infection sign (fever) is present - missing a
    heart problem is the costliest mistake, so that call stays in code."""
    if pick_id not in {d["id"] for d in config.get("departments") or []}:
        return "invalid"
    facts = list(facts)
    on_file = " ".join(f"{f.value or ''}".lower() for f in facts)
    # Facts are shown to the model as "kind: value"; a citation may keep that label.
    cited_values = [c.split(":", 1)[-1].strip().lower() for c in facts_used]
    if not any(c and c in on_file for c in cited_values):
        return "invalid"
    protected = (config.get("ai_routing") or {}).get("protected") or []
    complaint = _text(facts, ROUTING_KINDS)
    infection = any(_mentions(complaint, s) for s in (config.get("infection_routing") or {}).get("signs") or [])
    if (rules.basis == "keywords" and rules.department["id"] in protected
            and pick_id != rules.department["id"] and not infection):
        return "protected"
    return "used"


def doctor_choice(priority: str | None, emergency: bool = False) -> bool:
    """Whether the patient may pick which of the department's doctors they see."""
    return not emergency and priority not in NO_DOCTOR_CHOICE


def _start(slot: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(slot["start"]))


def by_earliest(slots: list[dict[str, Any]], open_cases: dict[str, int]) -> list[dict[str, Any]]:
    """Earliest first; at the same time, the doctor with fewer open cases first. Stable, so
    doctors tied on both keep roster order."""
    return sorted(slots, key=lambda s: (_start(s), open_cases.get(s.get("practitioner_id") or "", 0)))


def doctor_first(slots: list[dict[str, Any]], practitioner_id: str) -> list[dict[str, Any]]:
    """A follow-up's ordering: the previous doctor's times first, flagged, then everyone else's,
    each part keeping its order."""
    mine = [{**s, "previous_doctor": True} for s in slots if s.get("practitioner_id") == practitioner_id]
    return mine + [s for s in slots if s.get("practitioner_id") != practitioner_id]


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
    default_department = next((d for d in departments if d.get("default")), departments[0])

    if specialty_hint and specialty_hint in by_id:
        department, basis = by_id[specialty_hint], "rule_hint"
    else:
        facts = list(facts)
        complaint = _text(facts, ROUTING_KINDS)
        reason = _text(facts, {"reason_for_visit"})
        best_score = 0
        # The department with the most of its keywords in the current complaint wins (a match in
        # the stated reason for the visit counts double); a tie keeps the specialty_map order.
        for dep_id, keywords in (config.get("specialty_map") or {}).items():
            hits = [kw for kw in keywords if _mentions(complaint, kw)]
            score = len(hits) + sum(1 for kw in hits if _mentions(reason, kw))
            if hits and dep_id in by_id and score > best_score:
                department, matched, basis, best_score = by_id[dep_id], hits, "keywords", score
        infection = config.get("infection_routing") or {}
        signs = [s for s in infection.get("signs") or [] if _mentions(complaint, s)]
        if department is not None and signs and department["id"] in (infection.get("departments") or []):
            department, matched, basis = default_department, [*signs, *matched], "infection"

    if department is None:
        department = default_department

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