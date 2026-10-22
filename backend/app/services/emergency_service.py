"""What happens the moment a red-flag (emergency) rule matches, wherever it matches - the intake
turn (`intake_service`) or pre-screening (`workflows/prescreen`).

1. `flag` stamps the case once (`PatientCase.emergency_flagged_at`); from then on the patient is
   shown only "call an ambulance" and is never offered a booking.
2. `record_in_hms` writes an "EMERGENCY" note to the patient's OpenEMR chart straight away, so the
   hospital record shows it even if nobody ever opens the case in CareFlow (and the telemedicine
   guidelines' chat-record duty is met). It is the patient's own statements and the chat, labelled
   as not clinician-reviewed - never AI-written text. Idempotent and retried: pre-screening calls
   it again, so a note that failed during intake is written then.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.db import utcnow
from app.domain.intake_fields import PLACEHOLDERS
from app.integrations.hms import get_hms
from app.models import AuditEvent, PatientCase
from app.services import audit, case_repo, hospital_config

logger = logging.getLogger(__name__)

NOTE_TITLE = "CareFlow EMERGENCY - patient advised to call an ambulance"
WRITTEN = "emergency.recorded_in_hms"


def flag(db: Session, case: PatientCase, actor: str, rule_codes: list[str]) -> bool:
    """Stamp the case as an emergency. False when it already was. Caller commits."""
    if case.emergency_flagged_at is not None:
        return False
    case.emergency_flagged_at = utcnow()
    audit.record(db, case.id, actor, "emergency.flagged", {"rule_codes": rule_codes})
    return True


def render_note(db: Session, case: PatientCase, rule_codes: list[str]) -> str:
    tz_name = hospital_config.hospital().get("timezone") or "UTC"
    when = _local(case.emergency_flagged_at or utcnow(), tz_name)
    captured = case_repo.captured_fields(db, case.id)
    lines = [
        NOTE_TITLE, "=" * len(NOTE_TITLE), "",
        f"Flagged: {when} ({tz_name})",
        f"Advice shown to the patient: call an ambulance now on {hospital_config.ambulance_number()} "
        f"(or {hospital_config.emergency_number()}); no appointment was offered.",
        f"Clinic rule(s): {', '.join(rule_codes) or 'not recorded'}",
        "Source: patient-reported via CareFlow online intake. NOT reviewed by a clinician.",
        "",
    ]
    for label, kind in (("Age", "age"), ("Gender", "gender"), ("Reason for visit", "reason_for_visit"),
                        ("Symptoms", "symptom"), ("Duration", "duration"), ("History", "history")):
        values = [v for v in captured.get(kind) or [] if v not in PLACEHOLDERS]
        lines.append(f"{label}: {', '.join(values) if values else '(not given)'}")
    entries = [e for e in case_repo.clinical_entries(db, case.id) if e.name not in PLACEHOLDERS]
    for kind, label in (("medication", "Medications"), ("allergy", "Allergies")):
        named = [e.name + (f" ({e.reaction_or_dose})" if e.reaction_or_dose else "") for e in entries if e.kind == kind]
        lines.append(f"{label}: {', '.join(named) if named else '(not given)'}")
    session = case_repo.session_for(db, case)
    chat = [f"  {m.role}: {m.content}" for m in case_repo.messages(db, session.id) if m.turn_index > 0]
    lines += ["", "Intake conversation:", *(chat or ["  (none)"]), "", f"CareFlow case: {case.id}"]
    return "\n".join(lines)


def record_in_hms(db: Session, case: PatientCase, actor: str, rule_codes: list[str]) -> bool:
    """Write the emergency note to the chart once. Never raises: a failure is audited and the
    next call (pre-screening) retries it. True when the chart has the note."""
    if case.emergency_flagged_at is None or not case.hms_patient_id:
        return False
    already = db.query(AuditEvent.id).filter(AuditEvent.case_id == case.id, AuditEvent.action == WRITTEN).first()
    if already:
        return True
    try:
        reference = get_hms().push_document(
            case.hms_patient_id, NOTE_TITLE, render_note(db, case, rule_codes).encode("utf-8"), "text/plain",
        )
    except Exception as exc:  # noqa: BLE001 - the patient has already been told; never block that
        logger.warning("Emergency chart note failed (%s)", type(exc).__name__)
        audit.record(db, case.id, actor, "emergency.hms_record_failed", {"error_type": type(exc).__name__})
        db.commit()
        return False
    audit.record(db, case.id, actor, WRITTEN, {"reference": reference})
    db.commit()
    return True


def _local(moment: datetime, tz_name: str) -> str:
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
