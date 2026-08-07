"""Loader for hospital.yaml — the whole 'configurable hospital' surface.

Departments, doctors, appointment types, the specialty map and the triage rules
all live in one YAML file so the same code can simulate a different clinic
without any agent changes.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from config import settings


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return yaml.safe_load(settings.HOSPITAL_CONFIG_PATH.read_text(encoding="utf-8"))


def reload() -> dict[str, Any]:
    """Drop the cache — used by the seed script after editing the YAML."""
    load.cache_clear()
    return load()


def hospital() -> dict[str, Any]:
    return load().get("hospital", {})


def departments() -> list[dict[str, Any]]:
    return load().get("departments", [])


def doctors() -> list[dict[str, Any]]:
    return load().get("doctors", [])


def appointment_types() -> list[dict[str, Any]]:
    return load().get("appointment_types", [])


def specialty_map() -> dict[str, list[str]]:
    return load().get("specialty_map", {})


def triage_rules() -> dict[str, Any]:
    return load().get("triage_rules", {"version": "0", "rules": []})


def required_intake_fields() -> list[str]:
    return load().get("required_intake_fields", [])


def default_department() -> dict[str, Any] | None:
    for department in departments():
        if department.get("default"):
            return department
    return departments()[0] if departments() else None


def department_by_id(department_id: str | None) -> dict[str, Any] | None:
    return next((d for d in departments() if d["id"] == department_id), None)


def doctors_for_department(department_id: str) -> list[dict[str, Any]]:
    return [d for d in doctors() if d.get("department_id") == department_id]


def doctor_by_id(doctor_id: str | None) -> dict[str, Any] | None:
    return next((d for d in doctors() if d["id"] == doctor_id), None)


def appointment_type_for_priority(priority: str) -> str:
    mapping = load().get("priority_appointment_map", {})
    return mapping.get(priority, "routine_followup")


def appointment_type_by_id(type_id: str) -> dict[str, Any] | None:
    return next((a for a in appointment_types() if a["id"] == type_id), None)
