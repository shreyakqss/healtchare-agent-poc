"""Removes OpenEMR patients the test suite registered, so OpenEMR - and the admin dashboard's
"Patients on record" - holds only real records. Test-only: CareFlow itself never deletes a
patient. Uses the same direct database access as Admin > Doctors (provisioning.py).

Also drops the CareFlow cases that point at those patients. Chart documents' files stay on the
OpenEMR container's disk, unreferenced."""

from __future__ import annotations

from collections.abc import Iterable

from app.db import SessionLocal
from app.integrations.hms.openemr import provisioning
from app.models import ApplicationUser, IntakeSession, PatientCase

# Every table a registered test patient touches, with its patient column. Children first.
_PATIENT_ROWS = [
    ("form_soap", "pid"), ("forms", "pid"), ("form_encounter", "pid"), ("documents", "foreign_id"),
    ("lists", "pid"), ("pnotes", "pid"), ("openemr_postcalendar_events", "pc_pid"), ("patient_data", "pid"),
]
_WITH_UUIDS = [("patient_data", "pid"), ("documents", "foreign_id"), ("form_encounter", "pid")]


def delete_patients(mrns: Iterable[str]) -> int:
    """Delete these patients (OpenEMR public ids, as CareFlow stores them) from OpenEMR and
    their cases from CareFlow. Returns how many OpenEMR patients were removed."""
    wanted = sorted({str(m) for m in mrns if m})
    if not wanted:
        return 0
    marks = ", ".join(["%s"] * len(wanted))
    with provisioning._transaction() as cur:
        cur.execute(f"SELECT pid FROM patient_data WHERE pubpid IN ({marks})", wanted)
        pids = [row["pid"] for row in cur.fetchall()]
        if pids:
            in_pids = ", ".join(["%s"] * len(pids))
            for table, column in _WITH_UUIDS:
                cur.execute(
                    f"DELETE r FROM uuid_registry r JOIN {table} t ON t.uuid = r.uuid WHERE t.{column} IN ({in_pids})", pids,
                )
            for table, column in _PATIENT_ROWS:
                cur.execute(f"DELETE FROM {table} WHERE {column} IN ({in_pids})", pids)
    with SessionLocal() as db:
        sessions = [s for (s,) in db.query(PatientCase.session_id).filter(PatientCase.hms_patient_id.in_(wanted))]
        db.query(PatientCase).filter(PatientCase.hms_patient_id.in_(wanted)).delete(synchronize_session=False)
        db.query(IntakeSession).filter(IntakeSession.id.in_(sessions)).delete(synchronize_session=False)
        db.query(ApplicationUser).filter(ApplicationUser.hms_patient_id.in_(wanted)).update(
            {ApplicationUser.hms_patient_id: None}, synchronize_session=False,
        )
        db.commit()
    return len(pids)
