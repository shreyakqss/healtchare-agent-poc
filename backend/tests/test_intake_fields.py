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


def test_settle_values_are_distinct():
    assert f.settle_value("No, none at all") == f.NONE_REPORTED
    assert f.settle_value("you already asked me that, move on") == f.DECLINED
    assert f.settle_value("well it was my uncle who had it") == f.NOT_CAPTURED


def test_denial_requires_leading_no_or_phrase():
    assert f.is_denial("No")
    assert f.is_denial("I don't have any allergies")
    assert not f.is_denial("I was told no surgery was needed, but I have asthma")