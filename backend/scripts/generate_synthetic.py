"""Synthetic patient cases for the demo.

Everything here is invented. No real person, record, or clinical protocol is
represented, and no case is derived from real patient data.

Cases are built directly from fact rows and then run through the *rule-based*
parts of pre-screening only, so `seed.py` works with Ollama switched off.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from agents.care_navigator import navigate_care
from agents.summary_agent import build_plain_sections
from agents.urgency_evaluator import evaluate_urgency
from models import (
    AllergyMedication,
    AuditEvent,
    ClinicalSummary,
    IntakeMessage,
    IntakeSession,
    MedicalAttachment,
    PatientCase,
    PatientFact,
)

# (label, demographics, transcript, facts, allergies/meds, attachments, prescreen?)
SCENARIOS = [
    {
        "label": "low priority — routine dermatology",
        "demographics": {"age": 34, "sex": "F", "fixture_id": "SYN-001"},
        "turns": [
            ("patient", "I have a mild rash on my forearm."),
            ("assistant", "How long have you had the rash?"),
            ("patient", "About 2 days now. It itches a little."),
            ("assistant", "Do you have any existing medical conditions?"),
            ("patient", "No conditions. I don't take any medication and have no allergies."),
            ("assistant", "How would you prefer we contact you?"),
            ("patient", "Email is fine."),
        ],
        "facts": [
            ("reason_for_visit", "Mild rash on forearm", 0),
            ("symptom", "mild rash, itching", 0),
            ("duration", "about 2 days", 2),
            ("history", "no known conditions", 4),
            ("contact_preference", "email", 6),
        ],
        "entries": [],
        "attachments": [],
        "prescreen": True,
    },
    {
        "label": "medium priority — long-standing cough",
        "demographics": {"age": 51, "sex": "M", "fixture_id": "SYN-002"},
        "turns": [
            ("patient", "I've had a persistent cough that won't go away."),
            ("assistant", "How long has the cough lasted?"),
            ("patient", "About 3 weeks now."),
            ("assistant", "Do you have any existing medical conditions?"),
            ("patient", "I have asthma. I use an inhaler daily. No allergies."),
            ("assistant", "How would you prefer we contact you?"),
            ("patient", "Please call me."),
        ],
        "facts": [
            ("reason_for_visit", "Persistent cough", 0),
            ("symptom", "persistent cough", 0),
            ("duration", "about 3 weeks", 2),
            ("history", "asthma", 4),
            ("contact_preference", "phone call", 6),
        ],
        "entries": [("medication", "Salbutamol inhaler", "2 puffs daily", 4)],
        "attachments": [
            (
                "lab_report",
                "syn-002-lab-report.txt",
                "SYNTHETIC LAB REPORT (demo fixture)\n"
                "Patient: SYN-002\nPanel: Full blood count\n"
                "All values within the reference range for this synthetic fixture.\n"
                "This document is generated demonstration data.\n",
            )
        ],
        "prescreen": True,
    },
    {
        "label": "high priority — escalation symptom",
        "demographics": {"age": 62, "sex": "M", "fixture_id": "SYN-003"},
        "turns": [
            ("patient", "I've been having chest pain since this morning."),
            ("assistant", "How long has the chest pain lasted?"),
            ("patient", "Around 6 hours. It comes and goes."),
            ("assistant", "Do you have any existing medical conditions?"),
            ("patient", "I have hypertension. I take amlodipine. No allergies."),
            ("assistant", "How would you prefer we contact you?"),
            ("patient", "Phone."),
        ],
        "facts": [
            ("reason_for_visit", "Chest pain since this morning", 0),
            ("symptom", "chest pain", 0),
            ("duration", "around 6 hours", 2),
            ("history", "hypertension", 4),
            ("contact_preference", "phone call", 6),
        ],
        "entries": [("medication", "Amlodipine 5mg", "once daily", 4)],
        "attachments": [
            (
                "radiology",
                "syn-003-chest-xray.png",
                None,  # image: stored and displayed only, never interpreted
            )
        ],
        "prescreen": True,
    },
    {
        "label": "incomplete intake — still collecting",
        "demographics": {"age": 28, "sex": "F", "fixture_id": "SYN-004"},
        "turns": [
            ("patient", "My knee hurts after a fall."),
            ("assistant", "How long has the knee pain lasted?"),
        ],
        "facts": [
            ("reason_for_visit", "Knee pain after a fall", 0),
            ("symptom", "joint pain in knee", 0),
        ],
        "entries": [],
        "attachments": [],
        "prescreen": False,  # deliberately left mid-intake
    },
    {
        "label": "allergy / medication warning",
        "demographics": {"age": 45, "sex": "F", "fixture_id": "SYN-005"},
        "turns": [
            ("patient", "I have a sore throat and a mild fever."),
            ("assistant", "How long have you had these symptoms?"),
            ("patient", "About 4 days."),
            ("assistant", "Any allergies or medications we should know about?"),
            (
                "patient",
                "I'm allergic to penicillin. I'm currently taking Penicillin V that "
                "another clinic prescribed.",
            ),
            ("assistant", "How would you prefer we contact you?"),
            ("patient", "Email."),
        ],
        "facts": [
            ("reason_for_visit", "Sore throat and mild fever", 0),
            ("symptom", "sore throat, fever", 0),
            ("duration", "about 4 days", 2),
            ("history", "no known conditions", 4),
            ("contact_preference", "email", 6),
        ],
        "entries": [
            ("allergy", "Penicillin", "rash and swelling", 4),
            ("medication", "Penicillin V 250mg", "three times daily", 4),
        ],
        "attachments": [
            (
                "pathology",
                "syn-005-pathology-report.txt",
                "SYNTHETIC PATHOLOGY REPORT (demo fixture)\n"
                "Patient: SYN-005\nSpecimen: Throat swab\n"
                "This is generated demonstration data and carries no clinical meaning.\n",
            )
        ],
        "prescreen": True,
    },
]

# A 1x1 PNG. Enough for the UI to render an image attachment without shipping a
# binary fixture that looks like a real medical study.
PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6360000002000100ffff03000006"
    "000557bfabd40000000049454e44ae426082"
)


def _store_attachment(case_id, kind: str, filename: str, text: str | None):
    from services import extraction

    content = text.encode("utf-8") if text is not None else PLACEHOLDER_PNG
    return extraction.store(case_id, filename, content, kind)


def build_case(db: Session, scenario: dict) -> PatientCase:
    session = IntakeSession(
        status="INGESTING",
        consent_status="GRANTED",
    )
    db.add(session)
    db.flush()

    case = PatientCase(
        session_id=session.id,
        demographics_fixture=scenario["demographics"],
    )
    db.add(case)
    db.flush()

    for index, (role, content) in enumerate(scenario["turns"]):
        db.add(
            IntakeMessage(
                session_id=session.id, role=role, content=content, turn_index=index
            )
        )

    for kind, value, turn in scenario["facts"]:
        db.add(
            PatientFact(
                case_id=case.id,
                kind=kind,
                value=value,
                source_turn=turn,
                confidence=1.0,
            )
        )

    for kind, name, dose, turn in scenario["entries"]:
        db.add(
            AllergyMedication(
                case_id=case.id,
                kind=kind,
                name=name,
                reaction_or_dose=dose,
                source_turn=turn,
            )
        )

    for kind, filename, text in scenario["attachments"]:
        stored = _store_attachment(case.id, kind, filename, text)
        db.add(
            MedicalAttachment(
                case_id=case.id,
                kind=kind,
                filename=stored.filename,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                storage_uri=stored.storage_uri,
                extracted_text=stored.extracted_text,
                source_turn=0,
            )
        )

    db.add(
        AuditEvent(
            case_id=case.id,
            actor="seed",
            action="intake.session_started",
            payload={"scenario": scenario["label"], "synthetic": True},
        )
    )
    db.add(
        AuditEvent(
            case_id=case.id,
            actor="patient",
            action="intake.consent_recorded",
            payload={"consent_status": "GRANTED"},
        )
    )
    db.commit()
    db.refresh(case)

    if scenario["prescreen"]:
        _prescreen_offline(db, case, session)

    return case


def _prescreen_offline(db: Session, case: PatientCase, session: IntakeSession) -> None:
    """Run the parts of pre-screening that need no language model."""
    session.status = "ANALYZING"
    db.commit()

    triage = evaluate_urgency(db, case.id)
    navigate_care(
        db, case.id, triage.priority, getattr(triage, "specialty_hint", None)
    )

    facts = db.query(PatientFact).filter(PatientFact.case_id == case.id).all()
    entries = (
        db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case.id)
        .all()
    )

    sections = build_plain_sections(facts, entries)
    sections["administrative_priority"] = triage.priority
    sections["priority_warnings"] = triage.warnings or []

    db.add(
        ClinicalSummary(
            case_id=case.id,
            kind="prescreening",
            sections=sections,
            evidence=triage.evidence or [],
            missing_information=[],
        )
    )

    session.status = "NEEDS_REVIEW"
    db.add(
        AuditEvent(
            case_id=case.id,
            actor="seed",
            action="status.changed",
            payload={"from": "ANALYZING", "to": "NEEDS_REVIEW"},
        )
    )
    db.commit()


def generate_all(db: Session) -> list[PatientCase]:
    return [build_case(db, scenario) for scenario in SCENARIOS]
