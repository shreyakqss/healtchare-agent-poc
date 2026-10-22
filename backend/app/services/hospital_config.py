"""Hospital configuration: one YAML per clinic under `data/hospitals/`.

The file stem is the hospital id. Exactly one clinic is active at a time
(`active.txt`, gitignored, falling back to DEFAULT_HOSPITAL_ID). This is a demo
switch, not multi-tenancy.
"""

from __future__ import annotations

import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.core.errors import InvalidConfig, NotFound
from app.domain.intake_fields import FIELD_PROMPTS
from app.services.attachments import ATTACHMENT_KINDS

ACTIVE_POINTER = "active.txt"
PRIORITIES = {"high", "medium", "low"}
RULE_CONDITIONS = {"any_symptom", "all_symptoms", "any_history", "any_severity", "min_duration_days", "allergy_conflict"}


def _dir() -> Path:
    settings.HOSPITALS_DIR.mkdir(parents=True, exist_ok=True)
    return settings.HOSPITALS_DIR


def available() -> list[str]:
    return sorted(p.stem for p in _dir().glob("*.yaml"))


def path_for(hospital_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", hospital_id):
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
    hospital_details = config.get("hospital") or {}
    if not isinstance(hospital_details, dict) or any(
        not isinstance(hospital_details.get(field), str) or not hospital_details[field].strip()
        for field in ("id", "name")
    ):
        raise InvalidConfig("hospital needs a non-empty id and name.")
    if "timezone" in hospital_details and (
        not isinstance(hospital_details["timezone"], str) or not hospital_details["timezone"].strip()
    ):
        raise InvalidConfig("hospital timezone must be a non-empty IANA name.")
    facility_id = hospital_details.get("hms_facility_id")
    if facility_id is not None and (isinstance(facility_id, bool) or not isinstance(facility_id, int) or facility_id < 1):
        raise InvalidConfig("hospital hms_facility_id must be the hospital system's facility id (a positive number).")
    triage_config = config.get("triage_rules") or {}
    if not isinstance(triage_config, dict):
        raise InvalidConfig("triage_rules must be a mapping.")
    if not isinstance(triage_config.get("version"), str) or not triage_config["version"].strip():
        raise InvalidConfig("triage_rules needs a non-empty version.")
    rules = triage_config.get("rules") or []
    if not isinstance(rules, list) or not rules or not all(isinstance(rule, dict) for rule in rules):
        raise InvalidConfig("No triage rules defined.")
    rule_codes = [rule.get("code") for rule in rules]
    if any(not isinstance(code, str) or not code for code in rule_codes) or len(rule_codes) != len(set(rule_codes)):
        raise InvalidConfig("Every triage rule needs a unique code.")
    for rule in rules:
        if rule.get("priority") not in PRIORITIES:
            raise InvalidConfig(f"Rule {rule['code']} has an invalid priority.")
        condition = rule.get("condition") or {}
        if not isinstance(condition, dict) or set(condition) - RULE_CONDITIONS:
            raise InvalidConfig(f"Rule {rule['code']} has an invalid condition.")
        if "emergency" in rule and not isinstance(rule["emergency"], bool):
            raise InvalidConfig(f"Rule {rule['code']} has an invalid emergency value.")
        if rule.get("emergency") and rule.get("priority") != "high":
            raise InvalidConfig(f"Rule {rule['code']} is an emergency rule, so its priority must be high.")
        for key in ("any_symptom", "all_symptoms", "any_history", "any_severity"):
            values = condition.get(key, [])
            if not isinstance(values, list) or not all(isinstance(value, str) and value for value in values):
                raise InvalidConfig(f"Rule {rule['code']} has invalid {key} values.")
        duration = condition.get("min_duration_days")
        if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or duration < 0):
            raise InvalidConfig(f"Rule {rule['code']} has an invalid min_duration_days value.")
        if "allergy_conflict" in condition and not isinstance(condition["allergy_conflict"], bool):
            raise InvalidConfig(f"Rule {rule['code']} has an invalid allergy_conflict value.")
        if any(not isinstance(rule.get(field), str) or not rule[field].strip() for field in ("action", "explanation")):
            raise InvalidConfig(f"Rule {rule['code']} needs an action and explanation.")
    if not any(not (r.get("condition") or {}) for r in rules):
        raise InvalidConfig("No fallback rule (one with an empty `condition`).")

    departments = config.get("departments") or []
    if not isinstance(departments, list) or not departments or not all(isinstance(dep, dict) for dep in departments):
        raise InvalidConfig("No departments defined - there is nowhere to route a case.")
    department_ids = [dep.get("id") for dep in departments]
    if any(not isinstance(dep_id, str) or not dep_id for dep_id in department_ids) or len(department_ids) != len(set(department_ids)):
        raise InvalidConfig("Every department needs a unique id.")
    if any(not isinstance(dep.get("name"), str) or not dep["name"].strip() for dep in departments):
        raise InvalidConfig("Every department needs a name.")
    if sum(bool(dep.get("default")) for dep in departments) > 1:
        raise InvalidConfig("At most one department can be the default.")
    specialty_map = config.get("specialty_map") or {}
    doctors = config.get("doctors") or []
    if not isinstance(specialty_map, dict) or not all(
        isinstance(key, str)
        and isinstance(values, list)
        and all(isinstance(value, str) and value for value in values)
        for key, values in specialty_map.items()
    ):
        raise InvalidConfig("specialty_map must map department ids to keyword lists.")
    if not isinstance(doctors, list) or not all(isinstance(doctor, dict) for doctor in doctors):
        raise InvalidConfig("doctors must be a list of mappings.")
    doctor_ids = [doctor.get("id") for doctor in doctors]
    if any(not isinstance(value, str) or not value for value in doctor_ids) or len(doctor_ids) != len(set(doctor_ids)):
        raise InvalidConfig("Every configured doctor needs a unique id.")
    if any(not isinstance(doctor.get("name"), str) or not doctor["name"].strip() for doctor in doctors):
        raise InvalidConfig("Every configured doctor needs a name.")
    specialty_hints = [rule.get("specialty_hint") for rule in rules if rule.get("specialty_hint") is not None]
    doctor_departments = [doctor.get("department_id") for doctor in doctors]
    if not all(isinstance(value, str) and value for value in specialty_hints + doctor_departments):
        raise InvalidConfig("Routing references must be non-empty department ids.")
    unknown_hints = set(specialty_hints) - set(department_ids)
    unknown_routes = set(specialty_map) - set(department_ids)
    unknown_doctor_departments = set(doctor_departments) - set(department_ids)
    if unknown_hints or unknown_routes or unknown_doctor_departments:
        raise InvalidConfig("Routing configuration references an unknown department.")

    appointment_types = config.get("appointment_types") or []
    if not isinstance(appointment_types, list):
        raise InvalidConfig("appointment_types must be a list.")
    appointment_ids = [item.get("id") for item in appointment_types if isinstance(item, dict)]
    if len(appointment_ids) != len(appointment_types) or any(not isinstance(item, str) or not item for item in appointment_ids) or len(appointment_ids) != len(set(appointment_ids)):
        raise InvalidConfig("Every appointment type needs a unique id.")
    for item in appointment_types:
        duration = item.get("duration_minutes")
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            raise InvalidConfig("Every appointment type needs a label.")
        if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0):
            raise InvalidConfig("Appointment duration must be a positive number of minutes.")
    priority_map = config.get("priority_appointment_map") or {}
    if not isinstance(priority_map, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in priority_map.items()
    ):
        raise InvalidConfig("priority_appointment_map must be a mapping.")
    if set(priority_map) != PRIORITIES or set(priority_map.values()) - set(appointment_ids):
        raise InvalidConfig("priority_appointment_map must map every priority to a known appointment type.")

    required_fields = config.get("required_intake_fields") or []
    if not isinstance(required_fields, list) or not required_fields or not all(isinstance(field, str) for field in required_fields):
        raise InvalidConfig("No required_intake_fields defined.")
    unknown_fields = set(required_fields) - set(FIELD_PROMPTS)
    if unknown_fields or len(required_fields) != len(set(required_fields)):
        raise InvalidConfig(f"required_intake_fields contains unknown or duplicate fields: {sorted(unknown_fields)}")
    required_attachments = config.get("required_attachment_kinds") or []
    if not isinstance(required_attachments, list) or not all(isinstance(kind, str) for kind in required_attachments):
        raise InvalidConfig("required_attachment_kinds must be a list of known kinds.")
    unknown = set(required_attachments) - ATTACHMENT_KINDS
    if unknown or len(required_attachments) != len(set(required_attachments)):
        raise InvalidConfig(f"required_attachment_kinds contains unknown or duplicate kinds: {sorted(unknown)}")


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


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
    config = read(active_id())
    validate(config)
    return config


def reload() -> dict[str, Any]:
    load.cache_clear()
    return load()


def write_text(hospital_id: str, text: str) -> dict[str, Any]:
    try:
        config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InvalidConfig(f"Not valid YAML: {exc}") from exc
    validate(config)
    if config["hospital"]["id"] != hospital_id:
        raise InvalidConfig("hospital.id must match the configuration filename.")
    _atomic_write(path_for(hospital_id), text)
    if hospital_id == active_id():
        reload()
    return config


def write_json(hospital_id: str, config: dict[str, Any]) -> dict[str, Any]:
    validate(config)
    return write_text(hospital_id, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


def create(hospital_id: str, text: str | None = None) -> dict[str, Any]:
    if path_for(hospital_id).exists():
        raise InvalidConfig(f"Hospital {hospital_id} already exists.")
    if text is not None:
        return write_text(hospital_id, text)
    config = read(active_id())
    config["hospital"]["id"] = hospital_id
    return write_json(hospital_id, config)


def delete(hospital_id: str) -> None:
    if hospital_id == active_id():
        raise InvalidConfig("Cannot delete the active hospital - activate another first.")
    path_for(hospital_id).unlink(missing_ok=True)


def activate(hospital_id: str) -> dict[str, Any]:
    validate(read(hospital_id))
    _atomic_write(_dir() / ACTIVE_POINTER, hospital_id)
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

def required_attachment_kinds() -> list[str]:
    return load().get("required_attachment_kinds", [])

def triage_rules() -> dict[str, Any]:
    return load().get("triage_rules", {"version": "0", "rules": []})

def clinic_vocabulary() -> list[str]:
    """Every term the triage rules and the routing keywords match on.

    Handed to the extractor so a paraphrase is stored with the clinic's own term beside it.
    The terms stay clinic policy and the rule engine still decides; only the matching stops
    depending on the patient using the clinic's exact wording.
    """
    config = load()
    terms: set[str] = set()
    for rule in (config.get("triage_rules") or {}).get("rules") or []:
        condition = rule.get("condition") or {}
        for key in ("any_symptom", "all_symptoms", "any_history"):
            terms.update(condition.get(key) or [])
    for keywords in (config.get("specialty_map") or {}).values():
        terms.update(keywords)
    return sorted(terms)


def emergency_number() -> str:
    """The number a red-flag patient is told to call; India's national emergency line by default."""
    return str(hospital().get("emergency_number") or "112")


def ambulance_number() -> str:
    """The ambulance a red-flag patient is told to call; India's free ambulance line by default."""
    return str(hospital().get("ambulance_number") or "108")


def department_by_id(department_id: str | None) -> dict[str, Any] | None:
    return next((d for d in departments() if d["id"] == department_id), None)

def doctor_by_id(doctor_id: str | None) -> dict[str, Any] | None:
    return next((d for d in doctors() if d["id"] == doctor_id), None)
