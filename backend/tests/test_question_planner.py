"""The intake loop that made the assistant repeat itself.

The bug: the extractor records only what a patient *stated*, so "no, I don't
have any allergies" wrote no row at all — and a field with no row is
indistinguishable from one that was never asked. The planner therefore asked
again, and because the model rewords every question, it looked like a new one
each time ("history of heart disease?", "family history of heart problems?",
"any autoimmune disorders?") until the question ceiling ended the conversation
with an empty reply that rendered as nothing at all.

These run against SQLite in memory: `_settle_last_question` is pure state
management over three tables and needs neither Postgres nor a model to pin
down.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agents import question_planner as qp
from agents.symptom_extractor import is_empty_answer
from models import AllergyMedication, Base, IntakeMessage, PatientFact

REQUIRED = [
    "reason_for_visit",
    "symptom",
    "duration",
    "history",
    "medication",
    "allergy",
    "contact_preference",
]


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    # Only the three tables this touches: others carry Postgres JSONB columns
    # SQLite cannot render, and none of them are involved here. Their foreign
    # keys are inert — SQLite does not enforce them unless asked.
    Base.metadata.create_all(
        engine,
        tables=[
            IntakeMessage.__table__,
            PatientFact.__table__,
            AllergyMedication.__table__,
        ],
    )
    monkeypatch.setattr(
        qp.hospital_config, "required_intake_fields", lambda: list(REQUIRED)
    )
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def ids():
    return uuid.uuid4(), uuid.uuid4()  # case, session


def ask(db, session_id, field, turn, text="Do you have any of those?"):
    db.add(
        IntakeMessage(
            session_id=session_id,
            role="assistant",
            content=text,
            turn_index=turn,
            asks_field=field,
        )
    )
    db.commit()


def answer(db, session_id, text, turn):
    db.add(
        IntakeMessage(
            session_id=session_id, role="patient", content=text, turn_index=turn
        )
    )
    db.commit()


def test_a_denial_settles_the_field(db, ids):
    """The regression itself: "no" must not read as "not asked yet"."""
    case_id, session_id = ids
    ask(db, session_id, "history", 1)
    answer(db, session_id, "No, I don't have any past medical conditions.", 2)

    assert "history" in qp.missing_fields(db, case_id)
    qp._settle_last_question(db, case_id, session_id)
    assert "history" not in qp.missing_fields(db, case_id)

    fact = db.query(PatientFact).filter(PatientFact.case_id == case_id).one()
    assert fact.kind == "history"
    assert fact.value == qp.NONE_REPORTED
    assert fact.source_turn == 2  # traces to the turn they said it


def test_denied_allergies_are_recorded_as_none_known(db, ids):
    """Allergy and medication live in their own table, so they need their own row."""
    case_id, session_id = ids
    ask(db, session_id, "allergy", 1)
    answer(db, session_id, "Nope", 2)
    qp._settle_last_question(db, case_id, session_id)

    entry = db.query(AllergyMedication).filter(
        AllergyMedication.case_id == case_id
    ).one()
    assert (entry.kind, entry.name) == ("allergy", qp.NONE_REPORTED)
    assert "allergy" not in qp.missing_fields(db, case_id)


def test_a_real_answer_is_left_alone(db, ids):
    """When the extractor understood the reply, nothing is invented on top."""
    case_id, session_id = ids
    ask(db, session_id, "medication", 1)
    answer(db, session_id, "I take metformin for diabetes.", 2)
    db.add(
        AllergyMedication(
            case_id=case_id,
            kind="medication",
            name="metformin",
            reaction_or_dose=None,
            source_turn=2,
        )
    )
    db.commit()

    qp._settle_last_question(db, case_id, session_id)
    names = [e.name for e in db.query(AllergyMedication).all()]
    assert names == ["metformin"]


def test_nothing_settles_until_the_patient_replies(db, ids):
    """A question in flight is not an answer."""
    case_id, session_id = ids
    ask(db, session_id, "history", 1)
    qp._settle_last_question(db, case_id, session_id)
    assert db.query(PatientFact).count() == 0
    assert "history" in qp.missing_fields(db, case_id)


def test_asking_to_move_on_is_recorded_as_a_decline(db, ids):
    """Distinct from a denial: the clinician should see they were not answered."""
    case_id, session_id = ids
    ask(db, session_id, "history", 1)
    answer(db, session_id, "You are repeating your questions please go ahead", 2)
    qp._settle_last_question(db, case_id, session_id)

    fact = db.query(PatientFact).one()
    assert fact.value == qp.DECLINED
    assert "history" not in qp.missing_fields(db, case_id)


@pytest.mark.parametrize(
    "message",
    [
        "You are repeating your questions please go ahead",
        "Buddy you are repeating your questions again can you please move to the next steps",
        "I already told you that",
        "can we move on",
        "stop asking the same question",
    ],
)
def test_move_on_signals(message):
    assert qp.wants_to_move_on(message)


@pytest.mark.parametrize(
    "message",
    [
        "No",
        "I have had a headache for three days",
        "I take metformin for diabetes and amlodipine for blood pressure",
        "No, I don't have any known allergies",
    ],
)
def test_ordinary_answers_are_not_move_on_signals(message):
    assert not qp.wants_to_move_on(message)


@pytest.mark.parametrize(
    "message",
    [
        "No",
        "Nope",
        "no.",
        "None",
        "No, I don't have any ongoing health problems",
        "I don't have any allergies",
        "Not that I know of",
        "no known allergies",
    ],
)
def test_denials(message):
    assert qp.is_denial(message)


@pytest.mark.parametrize(
    "message",
    [
        "I have chest pain since this morning",
        "I take metformin for diabetes",
        "Yes, I had a heart attack in 2019",
        "Email is fine",
        # A "no" buried mid-sentence is not a denial of the question asked.
        "I get headaches but no dizziness with them",
    ],
)
def test_real_answers_are_not_denials(message):
    assert not qp.is_denial(message)


def test_an_unclear_answer_is_not_recorded_as_a_denial(db, ids):
    """The bug the first cut of this fix introduced.

    Settling every unextracted reply as "none reported" put a denial in the
    record for things the patient had actually described — a chest-pain case
    came out reading "symptom: None reported by patient". The field still has
    to close so the question does not repeat, but it closes pointing at the
    transcript rather than inventing a denial.
    """
    case_id, session_id = ids
    ask(db, session_id, "symptom", 1)
    answer(db, session_id, "It's a tight, heavy feeling right in the middle", 2)
    qp._settle_last_question(db, case_id, session_id)

    fact = db.query(PatientFact).one()
    assert fact.value == qp.NOT_CAPTURED
    assert fact.value != qp.NONE_REPORTED
    assert "symptom" not in qp.missing_fields(db, case_id)  # still no loop


@pytest.mark.parametrize("value", ["No", "none", "Nope.", "nothing", "N/A", " no "])
def test_bare_negations_are_not_stored_as_facts(value):
    """Otherwise "history: None" is filed next to the planner's real denial."""
    assert is_empty_answer(value)


@pytest.mark.parametrize(
    "value", ["chest pain", "no known allergies", "none of the above apply to me"]
)
def test_real_values_survive(value):
    assert not is_empty_answer(value)


def test_every_field_is_asked_at_most_once(db, ids):
    """The whole conversation, denied end to end, must still terminate.

    This is the shape of the reported transcript: the patient says no to
    everything. Before the fix it ran until the question ceiling; now each
    field settles on its answer and intake finishes in one pass.
    """
    case_id, session_id = ids
    turn = 0
    asked_fields = []

    for _ in range(50):  # far more than the 7 required fields
        outstanding = qp.missing_fields(db, case_id)
        if not outstanding:
            break
        field = outstanding[0]
        asked_fields.append(field)
        turn += 1
        ask(db, session_id, field, turn)
        turn += 1
        answer(db, session_id, "No", turn)
        qp._settle_last_question(db, case_id, session_id)
    else:
        pytest.fail("intake never completed — the repeat loop is still open")

    assert asked_fields == REQUIRED, "fields were re-asked or asked out of order"
    assert len(asked_fields) == len(set(asked_fields))
