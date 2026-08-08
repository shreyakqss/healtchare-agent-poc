"""The hospital config layer must not let a broken clinic reach disk.

The rule engine raises rather than guessing when nothing matches, so a config
without a fallback rule is a runtime failure waiting for the next patient.
These checks cover the file-level guards; the DB rule sync is exercised by
running the seed script.

Run from backend/:  pytest tests/
"""

import pytest
import yaml

from config import settings
from services import hospital_config
from services.hospital_config import ConfigError

VALID = {
    "hospital": {"id": "test-clinic", "name": "Test Clinic"},
    "departments": [{"id": "general", "name": "General", "default": True}],
    "triage_rules": {
        "version": "1",
        "rules": [
            {
                "code": "TR-HIGH-001",
                "priority": "high",
                "condition": {"any_symptom": ["chest pain"]},
                "action": "See today.",
                "explanation": "Escalated.",
            },
            {
                "code": "TR-LOW-000",
                "priority": "low",
                "condition": {},
                "action": "Routine slot.",
                "explanation": "Nothing matched.",
            },
        ],
    },
}


@pytest.fixture
def hospitals_dir(tmp_path, monkeypatch):
    """Point the loader at a scratch directory holding one valid clinic."""
    monkeypatch.setattr(settings, "HOSPITALS_DIR", tmp_path)
    monkeypatch.setattr(settings, "DEFAULT_HOSPITAL_ID", "test-clinic")
    (tmp_path / "test-clinic.yaml").write_text(yaml.safe_dump(VALID), encoding="utf-8")
    hospital_config.load.cache_clear()
    yield tmp_path
    hospital_config.load.cache_clear()


# --- validation ------------------------------------------------------------


def test_accepts_a_complete_config():
    hospital_config.validate(VALID)


def test_rejects_a_config_with_no_fallback_rule():
    """Without an empty-condition rule a case can match nothing at all."""
    config = yaml.safe_load(yaml.safe_dump(VALID))
    config["triage_rules"]["rules"] = [config["triage_rules"]["rules"][0]]
    with pytest.raises(ConfigError, match="fallback"):
        hospital_config.validate(config)


def test_rejects_a_config_with_no_rules():
    config = yaml.safe_load(yaml.safe_dump(VALID))
    config["triage_rules"]["rules"] = []
    with pytest.raises(ConfigError, match="triage rules"):
        hospital_config.validate(config)


def test_rejects_a_config_with_no_departments():
    config = yaml.safe_load(yaml.safe_dump(VALID))
    config["departments"] = []
    with pytest.raises(ConfigError, match="departments"):
        hospital_config.validate(config)


# --- file handling ---------------------------------------------------------


def test_rejects_path_traversal_in_a_hospital_id():
    with pytest.raises(ConfigError, match="Invalid hospital id"):
        hospital_config.path_for("../../etc/passwd")


def test_invalid_yaml_is_never_written(hospitals_dir):
    original = hospital_config.read_text("test-clinic")
    with pytest.raises(ConfigError):
        hospital_config.write_text("test-clinic", "departments: [oops")
    assert hospital_config.read_text("test-clinic") == original


def test_a_config_that_fails_validation_is_never_written(hospitals_dir):
    original = hospital_config.read_text("test-clinic")
    with pytest.raises(ConfigError, match="fallback"):
        hospital_config.write_text(
            "test-clinic",
            yaml.safe_dump(
                {
                    "departments": VALID["departments"],
                    "triage_rules": {
                        "version": "1",
                        "rules": [VALID["triage_rules"]["rules"][0]],
                    },
                }
            ),
        )
    assert hospital_config.read_text("test-clinic") == original


def test_create_copies_the_active_clinic(hospitals_dir):
    hospital_config.create("second-clinic")
    assert hospital_config.available() == ["second-clinic", "test-clinic"]
    assert hospital_config.read("second-clinic") == VALID


def test_create_refuses_to_overwrite(hospitals_dir):
    with pytest.raises(ConfigError, match="already exists"):
        hospital_config.create("test-clinic")


# --- activation ------------------------------------------------------------


def test_activate_switches_which_config_the_readers_answer_for(hospitals_dir):
    swapped = yaml.safe_load(yaml.safe_dump(VALID))
    swapped["hospital"]["name"] = "Second Clinic"
    hospital_config.create("second-clinic", yaml.safe_dump(swapped))

    assert hospital_config.hospital()["name"] == "Test Clinic"
    hospital_config.activate("second-clinic")
    assert hospital_config.active_id() == "second-clinic"
    assert hospital_config.hospital()["name"] == "Second Clinic"


def test_active_falls_back_to_the_default_when_the_pointer_is_stale(hospitals_dir):
    (hospitals_dir / hospital_config.ACTIVE_POINTER).write_text("deleted-clinic")
    assert hospital_config.active_id() == "test-clinic"


def test_cannot_delete_the_active_clinic(hospitals_dir):
    with pytest.raises(ConfigError, match="active"):
        hospital_config.delete("test-clinic")
