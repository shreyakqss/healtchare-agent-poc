"""Admin > Patients: the clinic's patient directory, one row per patient (by hospital record, MRN).

Administrative only - admin never gets clinical access (CLAUDE.md): who the patient is, which
department and doctor, when the visit is, and where the case stands. No complaint, symptom,
history, priority, note or AI text is copied in, and nothing here opens a case."""

from __future__ import annotations

from app.schemas.responses import AdminPatientItem, AdminPatientVisit, CaseListItem


def _when(item: CaseListItem):
    return item.appointment_start or item.created_at


def build(items: list[CaseListItem]) -> list[AdminPatientItem]:
    """Cases without a hospital record (an intake abandoned before the identity form) are left
    out - there is no patient to list yet. Most recent visit first."""
    by_patient: dict[str, list[CaseListItem]] = {}
    for item in items:
        if item.hms_patient_id:
            by_patient.setdefault(item.hms_patient_id, []).append(item)
    rows = []
    for mrn, cases in by_patient.items():
        cases.sort(key=_when, reverse=True)
        latest = cases[0]
        rows.append(AdminPatientItem(
            hms_patient_id=mrn, name=latest.demographics.get("name"), age=latest.demographics.get("age"),
            sex=latest.demographics.get("sex"), visit_count=len(cases),
            visits=[AdminPatientVisit(
                status=c.status, department_name=c.department_name, doctor_name=c.doctor_name,
                appointment_start=c.appointment_start, appointment_booked=c.appointment_booked, created_at=c.created_at,
            ) for c in cases],
        ))
    rows.sort(key=lambda r: r.visits[0].appointment_start or r.visits[0].created_at, reverse=True)
    return rows
