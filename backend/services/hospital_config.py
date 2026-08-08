"""Loader for the hospital YAMLs — the whole 'configurable hospital' surface.

Departments, doctors, appointment types, the specialty map and the triage rules
all live in one YAML file so the same code can simulate a different clinic
without any agent changes.

`settings.HOSPITALS_DIR` holds one YAML per clinic and **the file stem is the
hospital id** — that is what the API and the `TriageRule.hospital_id` scope are
keyed on. The `hospital.id` field inside the YAML is display metadata only, so
renaming a file is the one way to rename a hospital.

Exactly one hospital is active at a time (named in `active.txt`); every reader
below is parameterless and answers for whichever that is. Switching is a demo
action, not concurrent multi-tenancy — see `activate()`.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any
import yaml
from config import settings

ACTIVE_POINTER = "active.txt"


class ConfigError(ValueError):
    """The YAML is missing, unparseable, or would break the triage guarantee."""


def _dir() -> Path:
    settings.HOSPITALS_DIR.mkdir(parents=True, exist_ok=True)
    return settings.HOSPITALS_DIR


def available() -> list[str]:
    """Every configured hospital id, sorted."""
    return sorted(p.stem for p in _dir().glob("*.yaml"))


def path_for(hospital_id: str) -> Path:
    # Reject traversal outright: these ids arrive from the API.
    if hospital_id != Path(hospital_id).name or not hospital_id:
        raise ConfigError(f"Invalid hospital id: {hospital_id!r}")
    return _dir() / f"{hospital_id}.yaml"


def active_id() -> str:
    """The hospital every parameterless reader below answers for."""
    ids = available()
    if not ids:
        raise ConfigError(
            f"No hospital YAML found in {_dir()}. Restore one before starting "
            "the API — every case is routed against a configured clinic."
        )

    pointer = _dir() / ACTIVE_POINTER
    if pointer.exists():
        wanted = pointer.read_text(encoding="utf-8").strip()
        if wanted in ids:
            return wanted

    return settings.DEFAULT_HOSPITAL_ID if settings.DEFAULT_HOSPITAL_ID in ids else ids[0]


def validate(config: dict[str, Any]) -> None:
    """Reject a config that would break the 'every priority traces to a rule'
    guarantee. Same two checks the seed script has always enforced — they run
    here too so the editor cannot save a clinic the engine would raise on.
    """
    if not isinstance(config, dict):
        raise ConfigError("Top level of the config must be a YAML mapping.")

    rules = (config.get("triage_rules") or {}).get("rules") or []
    if not rules:
        raise ConfigError(
            "No triage rules defined. A priority must always trace to a "
            "configured rule, so an empty rule set is refused."
        )
    if not any(not (r.get("condition") or {}) for r in rules):
        raise ConfigError(
            "No fallback rule (one with an empty `condition`). Without it a "
            "case could match nothing and get no priority at all."
        )
    if not (config.get("departments") or []):
        raise ConfigError("No departments defined — there is nowhere to route a case.")


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return read(active_id())


def reload() -> dict[str, Any]:
    """Drop the cache — after editing a YAML or switching the active hospital."""
    load.cache_clear()
    return load()


# --- editing ---------------------------------------------------------------


def read(hospital_id: str) -> dict[str, Any]:
    path = path_for(hospital_id)
    if not path.exists():
        raise ConfigError(f"No such hospital: {hospital_id}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{hospital_id}.yaml is not valid YAML: {exc}") from exc


def read_text(hospital_id: str) -> str:
    path = path_for(hospital_id)
    if not path.exists():
        raise ConfigError(f"No such hospital: {hospital_id}")
    return path.read_text(encoding="utf-8")


def write_text(hospital_id: str, text: str) -> dict[str, Any]:
    """Parse, validate, then write. An invalid config never reaches disk."""
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Not valid YAML: {exc}") from exc

    validate(config)
    path_for(hospital_id).write_text(text, encoding="utf-8")
    if hospital_id == active_id():
        reload()
    return config


def create(hospital_id: str, text: str | None = None) -> dict[str, Any]:
    """New clinic, defaulting to a copy of the active one.

    Copying beats a blank file or a hand-written template: whatever is active
    already passes `validate`, so a new hospital is editable rather than broken
    on arrival.
    """
    path = path_for(hospital_id)
    if path.exists():
        raise ConfigError(f"Hospital {hospital_id} already exists.")
    return write_text(hospital_id, text if text is not None else read_text(active_id()))


def delete(hospital_id: str) -> None:
    if hospital_id == active_id():
        raise ConfigError("Cannot delete the active hospital — activate another first.")
    path_for(hospital_id).unlink(missing_ok=True)


def activate(hospital_id: str) -> dict[str, Any]:
    """Point `active.txt` at another clinic and drop the cache.

    Callers that own a DB session should follow this with
    `services.triage_rules.sync()`, or the new clinic's rules are not in the
    table the urgency evaluator reads.
    """
    validate(read(hospital_id))
    (_dir() / ACTIVE_POINTER).write_text(hospital_id, encoding="utf-8")
    return reload()


# --- readers (all answer for the active hospital) ---------------------------


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
