"""The configurable-hospital surface, so the frontend renders whatever
hospital.yaml currently describes rather than hardcoding a clinic."""

from __future__ import annotations

from fastapi import APIRouter

from services import hospital_config

router = APIRouter(prefix="/hospital", tags=["hospital"])


@router.get("/config")
def get_hospital_config():
    return {
        "hospital": hospital_config.hospital(),
        "departments": hospital_config.departments(),
        "doctors": hospital_config.doctors(),
        "appointment_types": hospital_config.appointment_types(),
        "required_intake_fields": hospital_config.required_intake_fields(),
        "triage_rules_version": hospital_config.triage_rules().get("version"),
    }
