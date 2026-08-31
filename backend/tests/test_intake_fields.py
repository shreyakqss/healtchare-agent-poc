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


def test_each_response_settles_a_field_differently():
    """A denial is clinical information, a refusal is not, and an unread answer is neither -
    so the three must stay distinct. `None` is the no-model case: it cannot claim either."""
    assert f.sentinel_for("denied") == f.NONE_REPORTED
    assert f.sentinel_for("declined") == f.DECLINED
    assert f.sentinel_for("answered") == f.NOT_CAPTURED
    assert f.sentinel_for("not_answered") is None
    assert f.sentinel_for(None) is None
