"""Care Navigator — recommends a department, doctor and appointment type.

Configuration-driven, not model-driven: the department comes from the keyword
map in hospital.yaml (or the triage rule's own hint), and the appointment type
comes from the priority map. Staff may override any of it.

The rationale text is written in code rather than generated, so the reason a
patient was routed somewhere is always reproducible.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import AuditEvent, PatientCase, PatientFact, RoutingRecommendation
from services import hospital_config, specialty_mapper


def navigate_care(
    db: Session, case_id, priority: str, specialty_hint: str | None = None
) -> RoutingRecommendation:
    facts = db.query(PatientFact).filter(PatientFact.case_id == case_id).all()

    department, matched_keywords = specialty_mapper.match_department(
        facts, specialty_hint
    )
    if department is None:
        raise RuntimeError("hospital.yaml defines no departments to route to.")

    doctor = specialty_mapper.pick_doctor(department["id"])
    appointment_type_id = hospital_config.appointment_type_for_priority(priority)
    appointment_type = hospital_config.appointment_type_by_id(appointment_type_id)

    if matched_keywords:
        basis = f"reported: {', '.join(matched_keywords)}"
    else:
        basis = "no specialty keywords matched, so the default department applies"

    rationale = (
        f"Routed to {department['name']} because {basis}. "
        f"Administrative priority '{priority}' maps to "
        f"{(appointment_type or {}).get('label', appointment_type_id)}. "
        f"{'Assigned to ' + doctor['name'] + '.' if doctor else 'No doctor is rostered for this department.'} "
        f"Advisory only — staff may accept or override this recommendation."
    )

    recommendation = RoutingRecommendation(
        case_id=case_id,
        specialty=department["name"],
        appointment_type=(appointment_type or {}).get("label", appointment_type_id),
        rationale=rationale,
        department_id=department["id"],
        doctor_id=doctor["id"] if doctor else None,
    )
    db.add(recommendation)

    case = db.get(PatientCase, case_id)
    if case is not None:
        case.specialty_hint = department["id"]

    db.add(
        AuditEvent(
            case_id=case_id,
            actor="system:care_navigator",
            action="routing.recommended",
            payload={
                "department_id": department["id"],
                "doctor_id": doctor["id"] if doctor else None,
                "appointment_type": appointment_type_id,
                "matched_keywords": matched_keywords,
            },
        )
    )
    db.commit()
    db.refresh(recommendation)
    return recommendation
