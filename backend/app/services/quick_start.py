"""Demo quick-start: fill a whole intake instantly instead of typing it turn by turn.

Writes exactly the same rows a real conversation would end up with - PatientFact and
AllergyMedication, source=patient, plus the HMS import a linked MRN triggers - so a
quick-started case is indistinguishable downstream from one a patient actually typed.
No LLM call is involved, so this works even with no API key configured.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.domain.intake_fields import NONE_REPORTED
from app.models import AllergyMedication, IntakeMessage, IntakeSession, PatientCase, PatientFact
from app.schemas.requests import StartSessionRequest
from app.services import audit, intake_service


@dataclass
class QuickStartPatient:
    key: str
    mrn: str
    opening_line: str
    facts: list[tuple[str, str]]  # (kind, value) - reason_for_visit/symptom/duration/contact_preference
    # Only needed for personas whose linked HMS record has nothing in that column -
    # closes the field with the same denial sentinel a real "no" answer would produce.
    deny_history: bool = False
    deny_medication: bool = False
    deny_allergy: bool = False
    closing_reply: str = "Thank you - that is everything I need. I am passing your answers to the care team now."


# Same six identities as frontend/src/features/intake/sample-patients.ts and the MRNs
# in data/hms/patients.yaml - picking one here pulls the same hospital record.
QUICK_START_PATIENTS: dict[str, QuickStartPatient] = {
    "arjun": QuickStartPatient(
        key="arjun", mrn="MRN-10021",
        opening_line="I've been having a tight chest pain since this morning. It comes and goes.",
        facts=[
            ("reason_for_visit", "chest pain"),
            ("symptom", "tight chest pain that comes and goes"),
            ("duration", "since this morning"),
            ("contact_preference", "phone"),
        ],
        # Arjun's HMS record has no allergies on file.
        deny_allergy=True,
    ),
    "priya": QuickStartPatient(
        key="priya", mrn="MRN-10022",
        opening_line="I have had a persistent cough for about three weeks now, with some wheezing at night.",
        facts=[
            ("reason_for_visit", "persistent cough"),
            ("symptom", "persistent cough"),
            ("symptom", "wheezing at night"),
            ("duration", "about three weeks"),
            ("contact_preference", "email"),
        ],
    ),
    "meera": QuickStartPatient(
        key="meera", mrn="MRN-10023",
        opening_line="I've had a fever and sore throat for two days. I started amoxicillin yesterday and I think I'm allergic to it.",
        facts=[
            ("reason_for_visit", "fever and sore throat"),
            ("symptom", "fever"),
            ("symptom", "sore throat"),
            ("duration", "two days"),
            ("contact_preference", "phone"),
        ],
    ),
    "dev": QuickStartPatient(
        key="dev", mrn="MRN-10024",
        opening_line="I've had a bad headache for about three weeks, mostly behind my eyes.",
        facts=[
            ("reason_for_visit", "headache"),
            ("symptom", "headache behind the eyes"),
            ("duration", "about three weeks"),
            ("contact_preference", "phone"),
        ],
        # Dev's HMS record has no conditions, medications or allergies on file.
        deny_history=True, deny_medication=True, deny_allergy=True,
    ),
    "kavita": QuickStartPatient(
        key="kavita", mrn="MRN-10025",
        opening_line="I've got an itchy rash on my arms. It started about four days ago after I changed washing powder.",
        facts=[
            ("reason_for_visit", "itchy rash on arms"),
            ("symptom", "itchy rash on both forearms"),
            ("duration", "about four days"),
            ("contact_preference", "text message"),
        ],
    ),
    "rohan": QuickStartPatient(
        key="rohan", mrn="MRN-10026",
        opening_line="My knee has been sore and swollen for about a week, especially going up stairs.",
        facts=[
            ("reason_for_visit", "sore, swollen knee"),
            ("symptom", "knee pain and swelling, worse on stairs"),
            ("duration", "about a week"),
            ("contact_preference", "phone"),
        ],
    ),
}


def create(db: Session, key: str) -> tuple[IntakeSession, PatientCase]:
    demo = QUICK_START_PATIENTS.get(key)
    if demo is None:
        raise NotFound(f"No quick-start patient {key!r}.")

    session, case = intake_service.start_session(db, StartSessionRequest(mrn=demo.mrn))
    intake_service.record_consent(db, session, case, True)

    db.add(IntakeMessage(session_id=session.id, role="patient", content=demo.opening_line, turn_index=0))
    db.add(IntakeMessage(session_id=session.id, role="assistant", content=demo.closing_reply, turn_index=1))

    for kind, value in demo.facts:
        db.add(PatientFact(case_id=case.id, kind=kind, value=value, source_turn=0))
    if demo.deny_history:
        db.add(PatientFact(case_id=case.id, kind="history", value=NONE_REPORTED, source_turn=0))
    if demo.deny_medication:
        db.add(AllergyMedication(case_id=case.id, kind="medication", name=NONE_REPORTED, source_turn=0))
    if demo.deny_allergy:
        db.add(AllergyMedication(case_id=case.id, kind="allergy", name=NONE_REPORTED, source_turn=0))

    audit.record(db, case.id, "system:quick_start", "intake.quick_started", {"key": key, "mrn": demo.mrn})
    db.commit()

    intake_service._sync_demographics(db, case)
    return session, case
