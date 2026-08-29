from dataclasses import dataclass

from app.domain import intake_fields as f


@dataclass
class Row:
    kind: str


REQUIRED = ["reason_for_visit", "symptom", "duration", "history", "medication", "allergy"]


def test_missing_fields_respects_entry_tables():
    missing = f.missing_fields(REQUIRED, [Row("reason_for_visit"), Row("symptom")], [Row("allergy")])
    assert missing == ["duration", "history", "medication"]


def test_condition_satisfies_history():
    assert "history" not in f.missing_fields(["history"], [Row("condition")], [])


def test_extract_duration_reads_common_phrasings():
    assert f.extract_duration("I have had a bad headache for three weeks.") == "for three weeks"
    assert f.extract_duration("chest pain since this morning") == "since this morning"
    assert f.extract_duration("it started about 2 days ago") == "about 2 days"
    assert f.extract_duration("a couple of months now") == "a couple of months"


def test_extract_duration_ignores_age_and_unrelated_numbers():
    # "34 years old" is an age; "2 tablets" has no time unit. Neither is a duration.
    assert f.extract_duration("I'm Dev Sharma, 34 years old") is None
    assert f.extract_duration("I take 2 tablets each morning") is None
    assert f.extract_duration("my head hurts") is None


def test_off_topic_questions_are_not_answers():
    assert f.is_off_topic("what are the 2026 movies")
    assert f.is_off_topic("What is the capital of France?")
    assert f.is_off_topic("Could you tell me a joke?")


def test_off_topic_does_not_flag_real_answers():
    # Deliberately conservative: any "<interrogative>...?" is treated as off-topic, even a
    # question about the patient's own symptom ("what does my headache mean?") - the assistant
    # is instructed never to diagnose anyway, so redirecting that case too is an acceptable
    # tradeoff for staying a simple, LLM-free check rather than a second model call to classify it.
    assert not f.is_off_topic("No")
    assert not f.is_off_topic("headache for three weeks")
    assert not f.is_off_topic("")


def test_settle_values_are_distinct():
    assert f.settle_value("No, none at all") == f.NONE_REPORTED
    assert f.settle_value("you already asked me that, move on") == f.DECLINED
    assert f.settle_value("well it was my uncle who had it") == f.NOT_CAPTURED


def test_denial_requires_leading_no_or_phrase():
    assert f.is_denial("No")
    assert f.is_denial("I don't have any allergies")
    assert not f.is_denial("I was told no surgery was needed, but I have asthma")

def test_a_complaint_is_not_an_administrative_request():
    """The opening line doubles as the symptom answer unless it is an errand. Getting this
    wrong is what made the assistant ask "what symptoms are you experiencing?" straight after
    the patient wrote "I have fever"."""
    for complaint in ("I have fever", "bad headache since Monday", "my ankle hurts",
                      "I've been coughing for a week"):
        assert not f.is_administrative_request(complaint), complaint


def test_an_errand_states_no_symptom():
    for errand in ("I need a refill of my blood pressure tablets", "here to collect my lab result",
                   "I need a medical certificate for work", "just a routine checkup",
                   "I came for my vaccination"):
        assert f.is_administrative_request(errand), errand
