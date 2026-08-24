"""Hospital configuration: one YAML per clinic under `data/hospitals/`.

The file stem is the hospital id. Exactly one clinic is active at a time
(`active.txt`, gitignored, falling back to DEFAULT_HOSPITAL_ID). This is a demo
switch, not multi-tenancy.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.core.errors import InvalidConfig, NotFound

ACTIVE_POINTER = "active.txt"


def _dir() -> Path:
    settings.HOSPITALS_DIR.mkdir(parents=True, exist_ok=True)
    return settings.HOSPITALS_DIR


def available() -> list[str]:
    return sorted(p.stem for p in _dir().glob("*.yaml"))


def path_for(hospital_id: str) -> Path:
    if not hospital_id or hospital_id != Path(hospital_id).name:
        raise InvalidConfig(f"Invalid hospital id: {hospital_id!r}")
    return _dir() / f"{hospital_id}.yaml"


def active_id() -> str:
    ids = available()
    if not ids:
        raise InvalidConfig(f"No hospital YAML found in {_dir()}.")
    pointer = _dir() / ACTIVE_POINTER
    if pointer.exists():
        wanted = pointer.read_text(encoding="utf-8").strip()
        if wanted in ids:
            return wanted
    return settings.DEFAULT_HOSPITAL_ID if settings.DEFAULT_HOSPITAL_ID in ids else ids[0]


def validate(config: Any) -> None:
    """Reject a config that would break 'every priority traces to a rule'."""
    if not isinstance(config, dict):
        raise InvalidConfig("Top level of the config must be a mapping.")
    rules = (config.get("triage_rules") or {}).get("rules") or []
    if not rules:
        raise InvalidConfig("No triage rules defined.")
    if not any(not (r.get("condition") or {}) for r in rules):
        raise InvalidConfig("No fallback rule (one with an empty `condition`).")
    if not (config.get("departments") or []):
        raise InvalidConfig("No departments defined - there is nowhere to route a case.")
    if not (config.get("required_intake_fields") or []):
        raise InvalidConfig("No required_intake_fields defined.")


def read(hospital_id: str) -> dict[str, Any]:
    path = path_for(hospital_id)
    if not path.exists():
        raise NotFound(f"No such hospital: {hospital_id}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise InvalidConfig(f"{hospital_id}.yaml is not valid YAML: {exc}") from exc


def read_text(hospital_id: str) -> str:
    path = path_for(hospital_id)
    if not path.exists():
        raise NotFound(f"No such hospital: {hospital_id}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return read(active_id())


def reload() -> dict[str, Any]:
    load.cache_clear()
    return load()


def write_text(hospital_id: str, text: str) -> dict[str, Any]:
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidConfig(f"Not valid YAML: {exc}") from exc
    validate(config)
    path_for(hospital_id).write_text(text, encoding="utf-8")
    if hospital_id == active_id():
        reload()
    return config


def write_json(hospital_id: str, config: dict[str, Any]) -> dict[str, Any]:
    validate(config)
    return write_text(hospital_id, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def create(hospital_id: str, text: str | None = None) -> dict[str, Any]:
    if path_for(hospital_id).exists():
        raise InvalidConfig(f"Hospital {hospital_id} already exists.")
    return write_text(hospital_id, text if text is not None else read_text(active_id()))


def delete(hospital_id: str) -> None:
    if hospital_id == active_id():
        raise InvalidConfig("Cannot delete the active hospital - activate another first.")
    path_for(hospital_id).unlink(missing_ok=True)


def activate(hospital_id: str) -> dict[str, Any]:
    validate(read(hospital_id))
    (_dir() / ACTIVE_POINTER).write_text(hospital_id, encoding="utf-8")
    return reload()


# --- readers for the active hospital ----------------------------------------

def hospital() -> dict[str, Any]:
    return load().get("hospital", {})

def departments() -> list[dict[str, Any]]:
    return load().get("departments", [])

def doctors() -> list[dict[str, Any]]:
    return load().get("doctors", [])

def appointment_types() -> list[dict[str, Any]]:
    return load().get("appointment_types", [])

def required_intake_fields() -> list[str]:
    return load().get("required_intake_fields", [])

def triage_rules() -> dict[str, Any]:
    return load().get("triage_rules", {"version": "0", "rules": []})

def department_by_id(department_id: str | None) -> dict[str, Any] | None:
    return next((d for d in departments() if d["id"] == department_id), None)

def doctor_by_id(doctor_id: str | None) -> dict[str, Any] | None:
    return next((d for d in doctors() if d["id"] == doctor_id), None)