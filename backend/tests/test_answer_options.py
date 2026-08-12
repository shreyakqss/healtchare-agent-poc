"""One-tap answers must save typing without putting words in a patient's mouth.

Two things are worth failing loudly on. A tapped duration that the rule engine
cannot parse silently loses the two-week escalation — the chip looks like an
answer and reaches triage as nothing. And a generated option is a sentence the
patient is about to file as their own statement, so it has to survive the same
cleaning whatever the model returns.
"""

import asyncio

import pytest

from services import answer_options, triage_engine


@pytest.mark.parametrize("option", answer_options.STATIC_OPTIONS["duration"])
def test_every_duration_chip_reaches_the_rule_engine(option):
    """A chip the engine cannot read is worse than no chip: it looks answered."""
    assert triage_engine.parse_duration_days(option) is not None, option


def test_two_week_chip_is_on_the_right_side_of_the_rule():
    """The clinic escalates at 14 days, so the chip saying so must clear it."""
    assert triage_engine.parse_duration_days("About 2 weeks") == 14
    assert triage_engine.parse_duration_days("About a week") == 7


def test_bounded_questions_answer_themselves():
    for field in ("gender", "contact_preference", "duration"):
        assert answer_options.static_for(field)
    # An open question has no fixed list — it is the model's to write, or none.
    assert answer_options.static_for("symptom") == []
    assert answer_options.static_for(None) == []


def test_contact_choices_ask_for_the_detail():
    assert answer_options.follow_up_for("contact_preference", "Phone")
    assert answer_options.follow_up_for("contact_preference", "Email")
    # Nothing else needs a second step.
    assert answer_options.follow_up_for("gender", "Male") is None


def test_generated_options_are_cleaned_before_a_patient_can_tap_one():
    messy = [
        "  It itches a lot.  ",
        "it itches a lot",  # same answer, different case
        "",
        "x" * 80,  # a sentence, not a chip
        "It is spreading",
        "It feels sore",
        "It comes and goes",
        "One option too many",
    ]
    cleaned = answer_options._clean(messy)
    assert cleaned == [
        "It itches a lot",
        "It is spreading",
        "It feels sore",
        "It comes and goes",
    ]
    assert len(cleaned) <= answer_options.MAX_OPTIONS


def test_nothing_is_offered_for_a_name_or_an_age():
    """Asked for these, the model invents them.

    It offered "John Smith" and "Jane Doe" to tap for a name, and age bands
    for an age. A tapped option is filed as the patient's own statement, so one
    tap would have put a false name in a clinical record. Both are free text,
    and the box for it was never taken away.
    """
    said = [{"role": "patient", "content": "I have a rash on my forearm."}]
    for field in ("name", "age"):
        options, source = asyncio.run(
            answer_options.suggest(field, "What is your name?", said)
        )
        assert options == []
        assert source == "none"


def test_a_question_about_no_field_gets_nothing():
    """The closing message asks for nothing, so it offers nothing."""
    said = [{"role": "patient", "content": "I have a rash on my forearm."}]
    assert asyncio.run(answer_options.suggest(None, "Thank you — that is all.", said)) == (
        [],
        "none",
    )


def test_no_options_are_generated_before_the_patient_has_said_anything():
    """The opening question is where inventing a complaint would do most harm.

    `asyncio.run` rather than a plugin: this is the only async test in the
    suite, and it needs no event-loop fixtures.
    """
    options, source = asyncio.run(
        answer_options.suggest("reason_for_visit", "What brings you in?", [])
    )
    assert options == []
    assert source == "none"
