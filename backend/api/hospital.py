"""The configurable-hospital surface, so the frontend renders whatever the
active hospital YAML currently describes rather than hardcoding a clinic.

`/config` is the read model every other page uses. The rest is the admin
surface: list the configured clinics, edit one as raw YAML, add another, and
switch which one is live. Saving or activating re-syncs that hospital's triage
rules into the DB, because `agents/urgency_evaluator.py` reads rows, not YAML.

No AuditEvent is written here: those rows require a case_id and a config change
belongs to no case. Add a nullable case_id if config history is ever wanted.
"""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import get_db
from services import hospital_config, triage_rules
from services.hospital_config import ConfigError

router = APIRouter(prefix="/hospital", tags=["hospital"])


class HospitalYaml(BaseModel):
    yaml_text: str = Field(min_length=1)


class NewHospital(BaseModel):
    # Becomes the file stem, so keep it path-safe; `path_for` rejects the rest.
    hospital_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    yaml_text: str | None = None


def _summary(hospital_id: str) -> dict:
    config = hospital_config.read(hospital_id)
    return {
        "id": hospital_id,
        "name": (config.get("hospital") or {}).get("name", hospital_id),
        "departments": len(config.get("departments") or []),
        "doctors": len(config.get("doctors") or []),
        "rules": len((config.get("triage_rules") or {}).get("rules") or []),
        "active": hospital_id == hospital_config.active_id(),
    }


@router.get("/config")
def get_hospital_config():
    return {
        "hospital": hospital_config.hospital(),
        "hospital_id": hospital_config.active_id(),
        "departments": hospital_config.departments(),
        "doctors": hospital_config.doctors(),
        "appointment_types": hospital_config.appointment_types(),
        "required_intake_fields": hospital_config.required_intake_fields(),
        "triage_rules_version": hospital_config.triage_rules().get("version"),
    }


@router.get("/hospitals")
def list_hospitals():
    try:
        return [_summary(hid) for hid in hospital_config.available()]
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/hospitals/{hospital_id}/yaml")
def get_hospital_yaml(hospital_id: str):
    try:
        return {
            "hospital_id": hospital_id,
            "yaml_text": hospital_config.read_text(hospital_id),
        }
    except ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/hospitals/{hospital_id}/yaml")
def save_hospital_yaml(
    hospital_id: str, body: HospitalYaml, db: Session = Depends(get_db)
):
    """Validate, then write. A config that would break triage is rejected with
    422 and never reaches disk."""
    try:
        hospital_config.write_text(hospital_id, body.yaml_text)
        triage_rules.sync(db, hospital_id)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary(hospital_id)


@router.get("/hospitals/{hospital_id}/json")
def get_hospital_json(hospital_id: str):
    """The same file as `/yaml`, parsed — what the visual builder edits.

    The builder needs a structured document, and PyYAML is already here; making
    the browser parse YAML instead would mean a second parser to keep honest.
    """
    try:
        return {"hospital_id": hospital_id, "config": hospital_config.read(hospital_id)}
    except ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/hospitals/{hospital_id}/json")
def save_hospital_json(hospital_id: str, body: dict, db: Session = Depends(get_db)):
    """Dump the builder's document back to YAML and save it through the same
    validate-then-write path as the raw editor.

    Round-tripping through a dict drops the file's comments — the Developer tab
    edits the text directly if those matter.
    """
    config = body.get("config")
    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="Body must be {'config': {...}}.")
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, width=100)
    try:
        hospital_config.write_text(hospital_id, text)
        triage_rules.sync(db, hospital_id)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary(hospital_id)


@router.post("/hospitals", status_code=201)
def create_hospital(body: NewHospital, db: Session = Depends(get_db)):
    """Add a clinic, defaulting to a copy of the active one so it arrives valid
    and editable rather than empty."""
    try:
        hospital_config.create(body.hospital_id, body.yaml_text)
        triage_rules.sync(db, body.hospital_id)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary(body.hospital_id)


@router.post("/hospitals/{hospital_id}/activate")
def activate_hospital(hospital_id: str, db: Session = Depends(get_db)):
    """Make this the clinic every agent routes against, and sync its rules.

    Existing cases keep the department and doctor ids they were routed to. Those
    ids come from the config that was active then, so a case opened after a
    switch can show an unresolved department — expected on a demo switch.
    """
    try:
        hospital_config.activate(hospital_id)
        triage_rules.sync(db, hospital_id)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary(hospital_id)


@router.delete("/hospitals/{hospital_id}", status_code=204)
def delete_hospital(hospital_id: str):
    """Remove a clinic's YAML. Its triage rules stay in the table so cases
    triaged under it keep resolving their rule codes."""
    try:
        hospital_config.delete(hospital_id)
    except ConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
