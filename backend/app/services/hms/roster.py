"""The effective doctor roster: live HMS practitioners overlaid on the YAML `doctors` list.

OpenEMR has no concept of CareFlow departments, so `HMSClient.list_practitioners()`
resolves `department_id` by matching PractitionerRole specialty text against the active
hospital's configured departments (see `integrations/hms/openemr/fhir.py`). Here:

- a department with at least one live practitioner uses the live list;
- a department with none keeps its YAML doctors (partial merge, no loss of coverage);
- a practitioner whose department is unresolved (`"unknown"`) is dropped;
- if the HMS is unreachable, the YAML roster is returned unchanged.

Used by both the prescreen `navigate_care` step (so routing picks a real practitioner)
and `GET /hospital/roster` (so the doctor workspace shows the same people).
"""

from __future__ import annotations

import logging
from typing import Any

from app.integrations.hms import get_hms
from app.services import hospital_config

logger = logging.getLogger(__name__)

Doctor = dict[str, Any]


def _department_index(departments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for dep in departments:
        index[str(dep.get("id", "")).lower()] = dep
        if dep.get("name"):
            index[str(dep["name"]).lower()] = dep
    return index


def effective_doctors_config(config: dict[str, Any]) -> dict[str, Any]:
    """`config` with its `doctors` list replaced per department by live practitioners.
    Soft-fails to the input on any HMS error."""
    try:
        practitioners = get_hms().list_practitioners()
    except Exception as exc:  # noqa: BLE001 - the YAML roster is the documented fallback
        logger.warning("Live practitioner lookup failed, using YAML doctors only (%s)", type(exc).__name__)
        return config

    by_key = _department_index(config.get("departments") or [])
    live: dict[str, list[Doctor]] = {}
    for practitioner in practitioners:
        department = by_key.get((practitioner.department_id or "").lower())
        if department is None:
            continue
        live.setdefault(department["id"], []).append({
            "id": practitioner.id,
            "name": practitioner.name,
            "department_id": department["id"],
            "specialty": practitioner.specialty,
            "working_days": practitioner.working_days,
            # Carried so the workspace can offer a clinician their own login name when they
            # sign a review or a note. YAML doctors have none, and stay None.
            "username": practitioner.username,
        })
    if not live:
        return config

    merged = [d for d in (config.get("doctors") or []) if d.get("department_id") not in live]
    for doctors in live.values():
        merged.extend(doctors)
    return {**config, "doctors": merged}


def effective_roster() -> tuple[str, list[Doctor]]:
    """`(source, doctors)` for the active hospital: `source` is `"hms"` when at least one
    department is served by live practitioners, else `"config"`."""
    config = hospital_config.load()
    merged = effective_doctors_config(config)
    source = "hms" if merged is not config else "config"
    return source, list(merged.get("doctors") or [])
