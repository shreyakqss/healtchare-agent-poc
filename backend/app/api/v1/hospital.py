"""Hospital configuration: read the active clinic, edit, create, activate, delete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.agents import llm_available
from app.api.deps import get_db
from app.core.errors import NotFound
from app.schemas.requests import HospitalYamlRequest, NewHospitalRequest
from app.schemas.responses import RosterDoctor, RosterResponse
from app.security import CurrentPrincipal, require_active_clinic, require_roles
from app.services import hospital_config, letterhead, triage_rules
from app.services.hms import effective_hospital, effective_roster

router = APIRouter(prefix="/hospital", tags=["hospital"])
PatientPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("patient"))]
ClinicianPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician"))]
AdminPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("admin"))]
StaffPrincipal = Annotated[CurrentPrincipal, Depends(require_roles("clinician", "admin"))]


def _summary(hospital_id: str) -> dict:
    cfg = hospital_config.read(hospital_id)
    return {
        "id": hospital_id,
        "name": (cfg.get("hospital") or {}).get("name", hospital_id),
        "active": hospital_id == hospital_config.active_id(),
        "departments": len(cfg.get("departments") or []),
        "doctors": len(cfg.get("doctors") or []),
        "rules": len((cfg.get("triage_rules") or {}).get("rules") or []),
        "has_letterhead": letterhead.exists(hospital_id),
    }


@router.get("/intake-config")
def intake_config(_: PatientPrincipal):
    cfg = hospital_config.load()
    hospital = effective_hospital()
    return {
        "hospital": {"id": hospital.get("id"), "name": hospital.get("name"), "timezone": hospital.get("timezone")},
        "required_intake_fields": cfg.get("required_intake_fields", []),
        "required_attachment_kinds": cfg.get("required_attachment_kinds", []),
        "llm_configured": llm_available(),
    }


@router.get("/config")
def active_config(principal: StaffPrincipal):
    """The active clinic. `hospital` is the hospital system's own facility record where it
    has one (`hospital.source == "hms"`); the rest is clinic policy from the YAML."""
    if "clinician" in principal.roles:
        require_active_clinic(principal)
    cfg = hospital_config.load()
    hospital_id = hospital_config.active_id()
    hospital = {**effective_hospital(), "has_letterhead": letterhead.exists(hospital_id)}
    return {"hospital_id": hospital_id, **cfg, "hospital": hospital}


@router.get("/roster", response_model=RosterResponse)
def roster(principal: ClinicianPrincipal):
    """The doctors a case can actually be routed to: live HMS practitioners where the
    hospital system knows them, the YAML roster elsewhere. Same merge the prescreen
    workflow uses, so the doctor workspace and routing agree."""
    require_active_clinic(principal)
    source, doctors = effective_roster()
    return RosterResponse(
        source=source,
        doctors=[
            RosterDoctor(id=d["id"], name=d["name"], department_id=d["department_id"],
                         specialty=d.get("specialty"), working_days=list(d.get("working_days") or []),
                         username=d.get("username"))
            for d in doctors
        ],
    )


@router.get("/hospitals")
def list_hospitals(_: AdminPrincipal):
    return [_summary(h) for h in hospital_config.available()]


@router.get("/hospitals/{hospital_id}/json")
def get_json(hospital_id: str, _: AdminPrincipal):
    return hospital_config.read(hospital_id)


@router.put("/hospitals/{hospital_id}/json")
def save_json(hospital_id: str, body: dict, _: AdminPrincipal, db: Session = Depends(get_db)):
    cfg = hospital_config.write_json(hospital_id, body)
    triage_rules.sync(db, hospital_id)
    return cfg


@router.get("/hospitals/{hospital_id}/yaml")
def get_yaml(hospital_id: str, _: AdminPrincipal):
    return {"hospital_id": hospital_id, "yaml": hospital_config.read_text(hospital_id)}


@router.put("/hospitals/{hospital_id}/yaml")
def save_yaml(hospital_id: str, body: HospitalYamlRequest, _: AdminPrincipal, db: Session = Depends(get_db)):
    cfg = hospital_config.write_text(hospital_id, body.yaml)
    triage_rules.sync(db, hospital_id)
    return cfg


@router.post("/hospitals", status_code=201)
def create_hospital(body: NewHospitalRequest, _: AdminPrincipal, db: Session = Depends(get_db)):
    hospital_config.create(body.hospital_id, body.yaml)
    triage_rules.sync(db, body.hospital_id)
    return _summary(body.hospital_id)


@router.post("/hospitals/{hospital_id}/activate")
def activate(hospital_id: str, _: AdminPrincipal, db: Session = Depends(get_db)):
    hospital_config.activate(hospital_id)
    triage_rules.sync(db, hospital_id)
    return _summary(hospital_id)


@router.delete("/hospitals/{hospital_id}", status_code=204, response_class=Response)
def delete_hospital(hospital_id: str, _: AdminPrincipal):
    hospital_config.delete(hospital_id)
    return Response(status_code=204)


@router.post("/hospitals/{hospital_id}/letterhead")
async def upload_letterhead(hospital_id: str, _: AdminPrincipal, file: UploadFile = File(...)):
    content = await file.read(letterhead.MAX_SIZE_BYTES + 1)
    letterhead.save(hospital_id, file.filename or "letterhead", content)
    return _summary(hospital_id)


@router.get("/hospitals/{hospital_id}/letterhead/file")
def letterhead_file(hospital_id: str, _: StaffPrincipal):
    """Any clinician can view it - it renders on the report they draft, not just in the
    admin editor that uploads it."""
    try:
        path = letterhead.path_for(hospital_id)
    except FileNotFoundError:
        raise NotFound("No letterhead uploaded for this clinic.") from None
    return FileResponse(path, content_disposition_type="inline")
