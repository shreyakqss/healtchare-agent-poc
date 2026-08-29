"""The live-doctors-over-YAML roster merge. Pure function tests - no DB, no live HMS."""

from unittest.mock import patch

from app.integrations.hms.schemas import HMSPractitioner
from app.services.hms.roster import effective_doctors_config, effective_roster

GET_HMS = "app.services.hms.roster.get_hms"

BASE_CONFIG = {
    "departments": [
        {"id": "general_medicine", "name": "General Medicine", "default": True},
        {"id": "cardiology", "name": "Cardiology"},
    ],
    "doctors": [
        {"id": "dr_mehta", "name": "Dr. A. Mehta", "department_id": "general_medicine"},
        {"id": "dr_rao", "name": "Dr. S. Rao", "department_id": "cardiology"},
    ],
}


def test_unknown_department_id_never_merges():
    """A practitioner whose specialty matched no configured department is dropped."""
    unmatched = HMSPractitioner(id="live-1", name="Dr. Live", department_id="unknown", working_days=[])
    with patch(GET_HMS) as mock_get_hms:
        mock_get_hms.return_value.list_practitioners.return_value = [unmatched]
        merged = effective_doctors_config(BASE_CONFIG)

    assert merged is BASE_CONFIG


def test_live_practitioner_lookup_failure_is_soft_and_returns_yaml_unchanged():
    with patch(GET_HMS) as mock_get_hms:
        mock_get_hms.return_value.list_practitioners.side_effect = RuntimeError("HMS unreachable")
        assert effective_doctors_config(BASE_CONFIG) is BASE_CONFIG


def test_matching_department_id_replaces_only_that_departments_doctors():
    live = HMSPractitioner(id="live-cardio-1", name="Dr. Live Cardiologist", department_id="cardiology", working_days=["mon", "tue"])
    with patch(GET_HMS) as mock_get_hms:
        mock_get_hms.return_value.list_practitioners.return_value = [live]
        merged = effective_doctors_config(BASE_CONFIG)

    by_department = {d["department_id"]: d for d in merged["doctors"]}
    assert by_department["cardiology"]["id"] == "live-cardio-1"
    assert by_department["cardiology"]["working_days"] == ["mon", "tue"]
    assert by_department["general_medicine"]["id"] == "dr_mehta"  # no live match - YAML kept


def test_department_name_matches_case_insensitively():
    live = HMSPractitioner(id="live-2", name="Dr. Live", department_id="CARDIOLOGY", working_days=[])
    with patch(GET_HMS) as mock_get_hms:
        mock_get_hms.return_value.list_practitioners.return_value = [live]
        merged = effective_doctors_config(BASE_CONFIG)
    assert any(d["id"] == "live-2" for d in merged["doctors"])


def test_effective_roster_reports_source():
    with patch("app.services.hms.roster.hospital_config.load", return_value=BASE_CONFIG):
        with patch(GET_HMS) as mock_get_hms:
            mock_get_hms.return_value.list_practitioners.return_value = []
            source, doctors = effective_roster()
    assert source == "config"
    assert [d["id"] for d in doctors] == ["dr_mehta", "dr_rao"]
