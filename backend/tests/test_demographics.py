"""Who the patient is, collected in the chat and shown where staff look.

Intake asks for name, age and gender like any other required field, so the
answers arrive as ordinary `PatientFact` rows. They are also copied onto the
case, because the queue and the case header read demographics, not facts — and
a row reading "Synthetic patient" for someone who gave their name three turns
ago is the feature looking broken exactly where it is looked at.
"""

from agents import question_planner as qp
from agents.symptom_extractor import DEMOGRAPHIC_KEYS, merge_demographics


def test_stated_details_are_copied_onto_the_case():
    merged = merge_demographics(
        {},
        [("name", "Dev Sharma"), ("age", "34"), ("gender", "male")],
    )
    # `sex` is the key the dashboard and case header already read.
    assert merged == {"name": "Dev Sharma", "age": "34", "sex": "male"}


def test_a_declined_answer_is_not_a_name():
    """Intake closes an unanswered field with a sentence. It is not a value."""
    for placeholder in (qp.DECLINED, qp.NONE_REPORTED, qp.NOT_CAPTURED):
        assert merge_demographics({}, [("name", placeholder)]) == {}


def test_the_first_value_wins():
    """A fixture set when the session opened outranks a later extraction.

    The simulation names its patients from the Synthea record at session start;
    an extractor that misreads a later turn must not rewrite who they are.
    """
    merged = merge_demographics(
        {"name": "Arjun Mehta", "age": 63},
        [("name", "Arjun"), ("age", "36"), ("gender", "male")],
    )
    assert merged == {"name": "Arjun Mehta", "age": 63, "sex": "male"}


def test_only_the_three_demographic_kinds_are_copied():
    assert set(DEMOGRAPHIC_KEYS) == {"name", "age", "gender"}
    assert merge_demographics({}, [("symptom", "chest pain")]) == {}


def test_intake_asks_for_each_of_them():
    """Every required field needs phrasing, or the prompt asks for "name"."""
    for field in ("name", "age", "gender"):
        assert field in qp.FIELD_PROMPTS
        # And each is satisfied by its own fact kind, so answering one does not
        # close the other two.
        assert qp.FIELD_SATISFIED_BY.get(field, {field}) == {field}
