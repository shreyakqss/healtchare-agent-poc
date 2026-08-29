from copy import deepcopy

import pytest
import yaml

from app.core.errors import InvalidConfig
from app.services import hospital_config


def test_active_hospital_config_passes_validation():
    hospital_config.validate(deepcopy(hospital_config.load()))


def test_duplicate_rule_codes_are_rejected():
    config = deepcopy(hospital_config.load())
    config["triage_rules"]["rules"][1]["code"] = config["triage_rules"]["rules"][0]["code"]
    with pytest.raises(InvalidConfig, match="unique code"):
        hospital_config.validate(config)


def test_broken_priority_appointment_reference_is_rejected():
    config = deepcopy(hospital_config.load())
    config["priority_appointment_map"]["high"] = "missing-type"
    with pytest.raises(InvalidConfig, match="known appointment type"):
        hospital_config.validate(config)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("triage_rules", "rules", 0, "condition", "any_symptom"), "chest pain", "any_symptom"),
        (("triage_rules", "rules", 0, "specialty_hint"), ["cardiology"], "Routing references"),
        (("priority_appointment_map", "high"), ["urgent_slot"], "must be a mapping"),
    ],
)
def test_malformed_nested_config_is_rejected(path, value, message):
    config = deepcopy(hospital_config.load())
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(InvalidConfig, match=message):
        hospital_config.validate(config)


def test_create_clone_rewrites_internal_hospital_id(monkeypatch, tmp_path):
    monkeypatch.setattr(hospital_config.settings, "HOSPITALS_DIR", tmp_path)
    source = deepcopy(hospital_config.load())
    source["hospital"]["id"] = "source"
    (tmp_path / "source.yaml").write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
    (tmp_path / hospital_config.ACTIVE_POINTER).write_text("source", encoding="utf-8")

    created = hospital_config.create("new-clinic")

    assert created["hospital"]["id"] == "new-clinic"
