"""Doctor-to-doctor referrals: a doctor who has seen the patient sends them on to another
department ("General Medicine thinks Cardiology should see this").

Signing a referral (the doctor's HMS password, as for a consultation note) opens a linked visit
in the target department, `PatientCase.visit_type="referral"`, and books it straight away with
the requested doctor (or the department's earliest free doctor) - no accept step. The patient
sees it under My visits and may change the time or doctor exactly as for a visit they booked
themselves (appointment_service.select_slot). The receiving doctor's case starts at review.

What reaches the receiving doctor:
- the patient's own statements, allergies and medicines - copied verbatim onto the new visit
  (`PatientFact` rows are added, never rewritten), because demographics, the worklist, triage and
  the clinician agents all read them from the case itself;
- a priority from `triage_engine` re-run on those statements: the referring doctor's "how soon"
  is shown and sent to the HMS, but never becomes a priority;
- the referring visit's signed consultation report(s), uploaded reports, AI file reads and
  intake conversation - linked, read from the referring case (`context_text`), never copied.
The AI differential and the patient projection get nothing extra; the patient sees only who
referred them and where.

The HMS gets a referral record (OpenEMR LBTref transaction) when the referral is signed - the one
chart write before a visit is released, because the receiving team needs it before then. It is
best effort: a failure is audited and never undoes the referral or the booking.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import Conflict, ServiceUnavailable, Unprocessable
from app.db import utcnow
from app.domain import routing as routing_rules
from app.domain import scheduling, triage_engine
from app.domain.lifecycle import CaseStatus
from app.integrations.hms import get_hms
from app.integrations.hms.schemas import ReferralRecord, VerifiedIdentity
from app.models import (
    AllergyMedication,
    CaseOwner,
    IntakeSession,
    PatientCase,
    PatientFact,
    Referral,
    RoutingRecommendation,
    TriageResult,
)
from app.services import (
    appointment_service,
    audit,
    case_repo,
    doctor_load,
    hospital_config,
    lifecycle,
    slot_hold_service,
    triage_rules,
)
from app.services.hms import effective_doctors_config

logger = logging.getLogger(__name__)

VISIT_TYPE = "referral"
URGENCIES = ("routine", "soon", "urgent")
# A visit that has ended without being seen cannot be referred on; one that was seen can,
# during or after the consultation (a COMPLETED visit included).
NOT_REFERRABLE = {CaseStatus.REJECTED, CaseStatus.FAILED}
OPEN = {CaseStatus.NEEDS_REVIEW, CaseStatus.APPROVED}


@dataclass(frozen=True)
class ReferralInput:
    to_department_id: str
    reason: str
    to_doctor_id: str | None = None
    question: str | None = None
    urgency: str = "routine"


def incoming(db: Session, case_id: uuid.UUID) -> Referral | None:
    """The referral that opened this visit, if it is a referred visit."""
    return db.query(Referral).filter(Referral.case_id == case_id).one_or_none()


def outgoing(db: Session, source_case_id: uuid.UUID) -> list[Referral]:
    """The referrals this visit's doctor(s) made, oldest first."""
    return (db.query(Referral).filter(Referral.source_case_id == source_case_id)
            .order_by(Referral.created_at).all())


def referred_by(referral: Referral | None) -> str | None:
    """One line for lists and the patient: who referred, from where. No clinical content."""
    if referral is None:
        return None
    return referral.from_doctor_name + (f", {referral.from_department_name}" if referral.from_department_name else "")


def state(db: Session, referral: Referral) -> dict:
    """Where the referral stands, read from the visit it opened - so it never goes stale."""
    case = db.get(PatientCase, referral.case_id)
    session = case_repo.session_for(db, case) if case else None
    routing = case_repo.latest_routing(db, referral.case_id) if case else None
    notes = case_repo.notes(db, referral.case_id) if case else []
    status = session.status if session else None
    booked = scheduling.chosen_slot(routing.slot_options or [], routing.selected_slot_id, routing.suggested_slot) if routing else None
    if status == CaseStatus.COMPLETED:
        label = "completed"
    elif status == CaseStatus.REJECTED:
        label = "cancelled"
    elif notes:
        label = "seen"
    elif case is not None and case.hms_appointment_id:
        label = "booked"
    else:
        label = "awaiting_time"
    # Closing the loop: once the receiving doctor has signed, the referring doctor sees the answer.
    outcome = notes[-1] if notes else None
    return {
        "status": label,
        "doctor_name": routing.doctor_name if routing else referral.to_doctor_name,
        "appointment_start": booked.get("start") if booked and case and case.hms_appointment_id else None,
        "outcome_diagnosis": outcome.diagnosis if outcome else None,
        "outcome_advice": outcome.follow_up_instructions if outcome else None,
        "outcome_by": outcome.doctor_name if outcome else None,
    }


def source_report(db: Session, referral: Referral) -> dict | None:
    """The referring doctor's latest signed report, for the receiving doctor's screen."""
    notes = case_repo.notes(db, referral.source_case_id)
    if not notes:
        return None
    n = notes[-1]
    return {"doctor_name": n.doctor_name, "signed_at": n.created_at, "notes": n.notes, "diagnosis": n.diagnosis,
            "prescription": n.prescription, "tests_ordered": n.tests_ordered, "advice": n.follow_up_instructions,
            "notes_for_doctors": n.referral_notes}


def context_text(db: Session, referral: Referral) -> str:
    """The referral and the referring visit's signed report(s), as plain lines for the receiving
    doctor's agents. Only what a doctor signed - never the AI differential."""
    lines = [
        f"REFERRAL from {referred_by(referral)} on {referral.created_at:%Y-%m-%d}"
        f" (how soon: {referral.urgency}): {referral.reason}",
    ]
    if referral.question:
        lines.append(f"Question for you: {referral.question}")
    for note in case_repo.notes(db, referral.source_case_id)[-1:]:
        lines.append(f"Referring doctor's signed consultation report ({note.doctor_name or 'doctor'}):")
        for label, value in (("Notes", note.notes), ("Diagnosis", note.diagnosis),
                             ("Prescription", note.prescription), ("Tests ordered", note.tests_ordered),
                             ("Advice/follow-up", note.follow_up_instructions),
                             ("Notes for other doctors", note.referral_notes)):
            if value and value.strip():
                lines.append(f"{label}: {value.strip()}")
    return "\n".join(lines)


# --- creating one --------------------------------------------------------------------------

def _validate(db: Session, source: PatientCase, data: ReferralInput, identity: VerifiedIdentity, config: dict):
    session = case_repo.session_for(db, source)
    if session.status in NOT_REFERRABLE:
        raise Conflict(f"A {session.status.lower()} visit cannot be referred on.")
    if not case_repo.notes(db, source.id):
        raise Conflict("Sign your consultation report first, so the next doctor has your findings.")
    if not source.hms_patient_id:
        raise Unprocessable("This visit is not linked to a hospital record, so it cannot be referred.")
    if data.urgency not in URGENCIES:
        raise Unprocessable(f"How soon must be one of: {', '.join(URGENCIES)}.")
    department = next((d for d in config.get("departments") or [] if d["id"] == data.to_department_id), None)
    if department is None:
        raise Unprocessable("Unknown department.")
    doctors = [d for d in config.get("doctors") or [] if d.get("department_id") == department["id"]]
    if not doctors:
        raise Conflict(f"{department['name']} has no doctor taking appointments.")
    wanted = None
    if data.to_doctor_id:
        wanted = next((d for d in doctors if d["id"] == data.to_doctor_id), None)
        if wanted is None:
            raise Unprocessable(f"That doctor is not in {department['name']}.")
        if wanted["id"] == identity.id:
            raise Conflict("You cannot refer a patient to yourself.")
    for existing in outgoing(db, source.id):
        child = db.get(PatientCase, existing.case_id)
        if (existing.to_department_id == department["id"] and child is not None
                and case_repo.session_for(db, child).status in OPEN):
            raise Conflict(f"This patient already has an open referral to {department['name']}.")
    return department, doctors, wanted


def _copy_statements(db: Session, source: PatientCase, case: PatientCase) -> int:
    """The patient's own words, verbatim, onto the referred visit (new rows; nothing rewritten)."""
    facts = case_repo.facts(db, source.id)
    for f in facts:
        db.add(PatientFact(case_id=case.id, kind=f.kind, value=f.value, normalized=f.normalized,
                           source=f.source, source_turn=f.source_turn, confidence=f.confidence))
    entries = case_repo.entries(db, source.id)
    for e in entries:
        db.add(AllergyMedication(case_id=case.id, kind=e.kind, name=e.name, reaction_or_dose=e.reaction_or_dose,
                                 source=e.source, source_turn=e.source_turn))
    db.flush()
    return len(facts) + len(entries)


def _triage(db: Session, case: PatientCase) -> str:
    """Priority from the clinic's rules on the carried statements - triage_engine alone sets it."""
    outcome = triage_engine.evaluate(
        case_repo.facts(db, case.id), case_repo.clinical_entries(db, case.id),
        triage_rules.active_rules(db, case.hospital_id),
    )
    db.add(TriageResult(case_id=case.id, priority=outcome.priority, rule_ids=outcome.rule_ids,
                        rule_codes=outcome.rule_codes, warnings=outcome.warnings, evidence=outcome.evidence,
                        emergency=outcome.emergency))
    audit.record(db, case.id, "system:urgency_evaluator", "triage.evaluated",
                 {"priority": outcome.priority, "rule_codes": outcome.rule_codes, "basis": "referral"})
    return outcome.priority


def _route(db: Session, case: PatientCase, department: dict, doctors: list[dict], wanted: dict | None,
           priority: str, config: dict, referral: Referral) -> tuple[RoutingRecommendation, dict | None]:
    """The referred visit's department and times, the asked-for doctor's first; the earliest
    free one is held. Returns the routing row and the held slot (None when nothing is free)."""
    open_cases = doctor_load.open_case_counts(db, [d["id"] for d in doctors], excluding_case=case.id)
    options = slot_hold_service.department_slots(db, get_hms(), department["id"], doctors, 8, case.id, open_cases, utcnow())
    if wanted:
        options = [s for s in options if s.get("practitioner_id") == wanted["id"]] + \
                  [s for s in options if s.get("practitioner_id") != wanted["id"]]
    slot = slot_hold_service.hold_first_free(db, case.id, options, f"doctor:{referral.from_doctor_id}")
    if slot is not None and slot.get("practitioner_id"):
        doctor = next((d for d in doctors if d["id"] == slot["practitioner_id"]), wanted or doctors[0])
        how = "asked for by the referring doctor" if wanted and doctor["id"] == wanted["id"] else "earliest free time"
    else:
        doctor = wanted or routing_rules.least_loaded(doctors, open_cases)
        how = "asked for by the referring doctor" if wanted else "no free time to go by, so the doctor with the fewest open cases"
    type_id = (config.get("priority_appointment_map") or {}).get(priority, "routine_followup")
    appointment_type = next((a for a in config.get("appointment_types") or [] if a["id"] == type_id),
                            {"id": type_id, "label": type_id.replace("_", " ").title()})
    rationale = routing_rules.with_doctor(
        f"Referred to {department['name']} by {referred_by(referral)}: {referral.reason.strip().rstrip('.')}. "
        f"Appointment type: {appointment_type['label']}. Advisory only - staff may accept or override.",
        doctor["name"], how,
    )
    routing = RoutingRecommendation(
        case_id=case.id, department_id=department["id"], department_name=department["name"],
        doctor_id=doctor["id"], doctor_name=doctor["name"],
        appointment_type_id=appointment_type["id"], appointment_type_label=appointment_type["label"],
        rationale=rationale, matched_keywords=[], suggested_slot=slot, slot_options=options,
    )
    db.add(routing)
    case.specialty_hint = department["id"]
    audit.record(db, case.id, f"doctor:{referral.from_doctor_id}", "routing.recommended",
                 {"department_id": department["id"], "doctor_id": doctor["id"], "basis": "referral",
                  "appointment_type": appointment_type["id"]})
    return routing, slot


def create(db: Session, source: PatientCase, data: ReferralInput, identity: VerifiedIdentity) -> Referral:
    """Refer the patient of `source` on; `identity` is the referring doctor, already verified.
    The visit it opens is committed before booking, so a booking failure never loses it."""
    config = effective_doctors_config(hospital_config.load())
    department, doctors, wanted = _validate(db, source, data, identity, config)
    actor = f"doctor:{identity.id}"
    source_session = case_repo.session_for(db, source)
    owner = db.query(CaseOwner).filter(CaseOwner.case_id == source.id).one()
    source_routing = case_repo.latest_routing(db, source.id)

    session = IntakeSession(status=CaseStatus.CREATED, consent_status=source_session.consent_status, channel=VISIT_TYPE)
    db.add(session)
    db.flush()
    case = PatientCase(session_id=session.id, hms_patient_id=source.hms_patient_id, hospital_id=source.hospital_id,
                       visit_type=VISIT_TYPE)
    db.add(case)
    db.flush()
    db.add(CaseOwner(case_id=case.id, user_id=owner.user_id))
    referral = Referral(
        source_case_id=source.id, case_id=case.id, from_doctor_id=identity.id, from_doctor_name=identity.name,
        from_department_name=source_routing.department_name if source_routing else None,
        to_department_id=department["id"], to_department_name=department["name"],
        to_doctor_id=wanted["id"] if wanted else None, to_doctor_name=wanted["name"] if wanted else None,
        reason=data.reason.strip(), question=(data.question or "").strip() or None, urgency=data.urgency,
    )
    db.add(referral)
    db.flush()
    audit.record(db, case.id, actor, "referral.received", {"referral_id": str(referral.id), "from_case": str(source.id)})
    carried = _copy_statements(db, source, case)
    priority = _triage(db, case)
    # The patient already gave their history; the referred visit starts at the doctor's review.
    for status in (CaseStatus.INGESTING, CaseStatus.ANALYZING, CaseStatus.NEEDS_REVIEW):
        lifecycle.transition(db, session, status, actor, case.id, commit=False)
    routing, slot = _route(db, case, department, doctors, wanted, priority, config, referral)
    audit.record(db, source.id, actor, "referral.created", {
        "referral_id": str(referral.id), "case_id": str(case.id), "to_department": department["id"],
        "to_doctor": referral.to_doctor_id, "urgency": data.urgency, "carried_statements": carried,
    })
    db.commit()

    if slot is not None and slot.get("practitioner_id"):
        _book(db, case, routing, slot, actor)
    _record_in_hms(db, referral, source, actor)
    db.refresh(referral)
    return referral


def _book(db: Session, case: PatientCase, routing: RoutingRecommendation, slot: dict, actor: str) -> None:
    """Book the held time on the doctor's calendar. On failure the hold stays and the patient
    picks a time themselves, as for any visit whose booking did not go through."""
    try:
        reference = appointment_service.book(db, case, slot, routing.department_name)
    except (ServiceUnavailable, Unprocessable) as exc:
        logger.warning("Referral booking failed (%s)", type(exc).__name__)
        audit.record(db, case.id, actor, "appointment.booking_failed", {"slot_id": slot.get("id")})
        db.commit()
        return
    routing = db.get(RoutingRecommendation, routing.id)
    routing.selected_slot_id = slot.get("id")
    case = db.get(PatientCase, case.id)
    case.hms_appointment_id = reference
    audit.record(db, case.id, actor, "appointment.booked",
                 {"slot_id": slot.get("id"), "practitioner_id": slot.get("practitioner_id"),
                  "hms_appointment_id": reference, "basis": "referral"})
    db.commit()


def _record_in_hms(db: Session, referral: Referral, source: PatientCase, actor: str) -> None:
    notes = case_repo.notes(db, source.id)
    routing = case_repo.latest_routing(db, referral.case_id)
    try:
        referral.hms_reference = get_hms().record_referral(ReferralRecord(
            patient_mrn=source.hms_patient_id or "", from_practitioner_id=referral.from_doctor_id,
            to_practitioner_id=routing.doctor_id if routing else referral.to_doctor_id,
            to_department=referral.to_department_name,
            reason=referral.reason + (f"\nQuestion: {referral.question}" if referral.question else ""),
            diagnosis=(notes[-1].diagnosis if notes else None), urgency=referral.urgency,
            referred_on=datetime.now().date(),
        ))
        audit.record(db, referral.source_case_id, actor, "referral.hms_recorded", {"reference": referral.hms_reference})
    except Exception as exc:  # noqa: BLE001 - the referral and booking stand; staff can file it by hand
        logger.warning("Referral not recorded in the HMS (%s)", type(exc).__name__)
        audit.record(db, referral.source_case_id, actor, "referral.hms_record_failed", {"error_type": type(exc).__name__})
    db.commit()
