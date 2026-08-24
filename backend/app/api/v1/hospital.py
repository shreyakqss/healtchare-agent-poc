"""Hospital configuration: read the active clinic, edit, create, activate, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.requests import HospitalYamlRequest, NewHospitalRequest
from app.services import hospital_config, triage_rules

router = APIRouter(prefix="/hospital", tags=["hospital"])


def _summary(hospital_id: str) -> dict:
    cfg = hospital_config.read(hospital_id)
    return {
        "id": hospital_id,
        "name": (cfg.get("hospital") or {}).get("name", hospital_id),
        "active": hospital_id == hospital_config.active_id(),
        "departments": len(cfg.get("departments") or []),
        "doctors": len(cfg.get("doctors") or []),
        "rules": len((cfg.get("triage_rules") or {}).get("rules") or []),
    }


@router.get("/config")
def active_config():
    cfg = hospital_config.load()
    return {"hospital_id": hospital_config.active_id(), **cfg}


@router.get("/hospitals")
def list_hospitals():
    return [_summary(h) for h in hospital_config.available()]


@router.get("/hospitals/{hospital_id}/json")
def get_json(hospital_id: str):
    return hospital_config.read(hospital_id)


@router.put("/hospitals/{hospital_id}/json")
def save_json(hospital_id: str, body: dict, db: Session = Depends(get_db)):
    cfg = hospital_config.write_json(hospital_id, body)
    triage_rules.sync(db, hospital_id)
    return cfg


@router.get("/hospitals/{hospital_id}/yaml")
def get_yaml(hospital_id: str):
    return {"hospital_id": hospital_id, "yaml": hospital_config.read_text(hospital_id)}


@router.put("/hospitals/{hospital_id}/yaml")
def save_yaml(hospital_id: str, body: HospitalYamlRequest, db: Session = Depends(get_db)):
    cfg = hospital_config.write_text(hospital_id, body.yaml)
    triage_rules.sync(db, hospital_id)
    return cfg


@router.post("/hospitals", status_code=201)
def create_hospital(body: NewHospitalRequest, db: Session = Depends(get_db)):
    hospital_config.create(body.hospital_id, body.yaml)
    triage_rules.sync(db, body.hospital_id)
    return _summary(body.hospital_id)


@router.post("/hospitals/{hospital_id}/activate")
def activate(hospital_id: str, db: Session = Depends(get_db)):
    hospital_config.activate(hospital_id)
    triage_rules.sync(db, hospital_id)
    return _summary(hospital_id)


@router.delete("/hospitals/{hospital_id}", status_code=204, response_class=Response)
def delete_hospital(hospital_id: str):
    hospital_config.delete(hospital_id)
    return Response(status_code=204)