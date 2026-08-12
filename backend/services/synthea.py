"""Synthetic patient records, from Synthea.

The simulated patients are Synthea records (github.com/synthetichealth/synthea)
— a generated population, not hand-written dialogue. Two sources, one shape:

1. **A real Synthea export**, if `backend/data/synthea/csv/` exists. Run Synthea
   with `./run_synthea -p 25 --exporter.csv.export true` and copy its
   `output/csv/` here. The columns read below are Synthea's own.
2. **The bundled fixture**, `backend/data/patients.yaml`, otherwise — the same
   records in YAML so the demo runs without a Java toolchain. Its comments map
   each block back to the CSV it mirrors.

Only the fields the intake conversation can actually use are read: demographics,
active conditions, active medications, allergies, and the reason for the most
recent encounter. Synthea generates far more (claims, payers, providers,
observations, care plans); none of it belongs in a patient's answer to "what
brings you in today", so none of it is loaded.

Nothing here is real. Synthea's populations are statistically generated and
contain no real person, and the fixtures are invented.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config import BASE_DIR

logger = logging.getLogger(__name__)

CSV_DIR: Path = BASE_DIR / "data" / "synthea" / "csv"
FIXTURE_FILE: Path = BASE_DIR / "data" / "patients.yaml"

# How many patients to take from an export. Synthea will happily generate
# thousands; the simulation runs two or three at a time.
MAX_PATIENTS = 12

# Synthea suffixes generated names with digits ("Arjun123") so they cannot be
# mistaken for real ones. Useful in a database, unreadable in a chat window.
_NAME_DIGITS = re.compile(r"\d+$")
# Clinical descriptions carry a SNOMED qualifier: "Asthma (disorder)".
_QUALIFIER = re.compile(r"\s*\((disorder|finding|situation|procedure)\)\s*$", re.I)


@dataclass
class Coded:
    """One coded clinical entry — SNOMED CT, RxNorm, whatever the file used."""

    code: str
    description: str


@dataclass
class SyntheaPatient:
    id: str
    first: str
    last: str
    birthdate: str
    gender: str
    age: int
    reason: str
    """Reason for the encounter — what the patient came in about."""
    duration_days: float
    """How long ago the encounter started. Drives the duration answer."""
    conditions: list[Coded] = field(default_factory=list)
    medications: list[Coded] = field(default_factory=list)
    allergies: list[Coded] = field(default_factory=list)
    # Not in a Synthea record: how someone talks. See patients.yaml.
    style: str = "calm and cooperative"
    opening: str = ""
    symptom: str = ""
    contact_preference: str = "a phone call"
    headline: str = ""
    expectation: str = ""

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()


def clean(description: str) -> str:
    return _QUALIFIER.sub("", (description or "").strip())


def _age(birthdate: str) -> int:
    try:
        born = datetime.fromisoformat(birthdate)
    except (TypeError, ValueError):
        return 0
    today = datetime.now(timezone.utc).date()
    return max(
        0,
        today.year - born.year - ((today.month, today.day) < (born.month, born.day)),
    )


# --- source 1: a real Synthea CSV export -----------------------------------


def _rows(name: str) -> list[dict[str, str]]:
    path = CSV_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        # Synthea's headers are upper case, but its own exporters have shipped
        # both cases over the years; normalising once here is cheaper than
        # guessing at every read site.
        return [{(k or "").upper(): v for k, v in row.items()} for row in csv.DictReader(handle)]


def _by_patient(rows: list[dict[str, str]], *, active_only: bool = True) -> dict[str, list[Coded]]:
    """Group coded rows by patient, keeping only entries that have not stopped.

    A resolved condition or a finished course of medication is history, not
    something a patient would report as current, and reporting it as current is
    what would put a wrong statement in the record.
    """
    grouped: dict[str, list[Coded]] = {}
    for row in rows:
        if active_only and (row.get("STOP") or "").strip():
            continue
        description = clean(row.get("DESCRIPTION", ""))
        if not description:
            continue
        grouped.setdefault(row.get("PATIENT", ""), []).append(
            Coded(code=(row.get("CODE") or "").strip(), description=description)
        )
    return grouped


def _latest_encounter(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """The most recent encounter per patient that records why it happened.

    Synthea writes a reason on some encounter classes and not others; an
    encounter with no reason cannot be the thing a patient is calling about.
    """
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        if not (row.get("REASONDESCRIPTION") or "").strip():
            continue
        patient = row.get("PATIENT", "")
        current = latest.get(patient)
        if current is None or (row.get("START", "") > current.get("START", "")):
            latest[patient] = row
    return latest


def _days_since(timestamp: str) -> float:
    try:
        started = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return 1.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds() / 86400)


def _from_csv() -> list[SyntheaPatient]:
    patients = _rows("patients.csv")
    if not patients:
        return []

    conditions = _by_patient(_rows("conditions.csv"))
    medications = _by_patient(_rows("medications.csv"))
    allergies = _by_patient(_rows("allergies.csv"))
    encounters = _latest_encounter(_rows("encounters.csv"))

    loaded: list[SyntheaPatient] = []
    for row in patients:
        patient_id = row.get("ID") or row.get("PATIENT") or ""
        encounter = encounters.get(patient_id)
        if encounter is None:
            # No stated reason for any visit, so nothing to walk in and say.
            continue
        if (row.get("DEATHDATE") or "").strip():
            continue

        first = _NAME_DIGITS.sub("", row.get("FIRST", "").strip())
        last = _NAME_DIGITS.sub("", row.get("LAST", "").strip())
        reason = clean(encounter.get("REASONDESCRIPTION", ""))

        loaded.append(
            SyntheaPatient(
                id=patient_id,
                first=first or "Patient",
                last=last,
                birthdate=row.get("BIRTHDATE", ""),
                gender=(row.get("GENDER") or "").upper(),
                age=_age(row.get("BIRTHDATE", "")),
                reason=reason,
                duration_days=_days_since(encounter.get("START", "")),
                conditions=conditions.get(patient_id, []),
                medications=medications.get(patient_id, []),
                allergies=allergies.get(patient_id, []),
                # Synthea records no manner of speaking and no symptom prose,
                # so the persona is the plainest thing the record supports.
                opening=f"I'm here about {reason.lower()}." if reason else "",
                symptom=reason.lower(),
                headline=reason,
                expectation="From a Synthea export",
            )
        )
        if len(loaded) >= MAX_PATIENTS:
            break
    return loaded


# --- source 2: the bundled fixture -----------------------------------------


def _coded(entries: Any) -> list[Coded]:
    return [
        Coded(code=str(entry.get("code", "")), description=clean(entry.get("description", "")))
        for entry in (entries or [])
        if entry.get("description")
    ]


def _from_fixture() -> list[SyntheaPatient]:
    if not FIXTURE_FILE.exists():
        return []
    raw: Any = yaml.safe_load(FIXTURE_FILE.read_text(encoding="utf-8")) or {}

    loaded: list[SyntheaPatient] = []
    for entry in raw.get("patients") or []:
        record = entry.get("record") or {}
        persona = entry.get("persona") or {}
        encounter = record.get("encounter") or {}
        birthdate = str(record.get("birthdate", ""))
        loaded.append(
            SyntheaPatient(
                id=entry["id"],
                first=record.get("first", ""),
                last=record.get("last", ""),
                birthdate=birthdate,
                gender=(record.get("gender") or "").upper(),
                age=_age(birthdate),
                reason=clean(encounter.get("reason", "")),
                duration_days=float(encounter.get("duration_days", 1)),
                conditions=_coded(record.get("conditions")),
                medications=_coded(record.get("medications")),
                allergies=_coded(record.get("allergies")),
                style=persona.get("style", "calm and cooperative"),
                opening=persona.get("opening", ""),
                symptom=persona.get("symptom", ""),
                contact_preference=persona.get("contact_preference", "a phone call"),
                headline=entry.get("headline", ""),
                expectation=entry.get("expectation", ""),
            )
        )
    return loaded


# --- the one reader --------------------------------------------------------


@lru_cache(maxsize=1)
def patients() -> tuple[str, dict[str, SyntheaPatient]]:
    """(source, patients by id). A real export wins over the fixture."""
    exported = _from_csv()
    if exported:
        logger.info("Loaded %d Synthea patients from %s", len(exported), CSV_DIR)
        return "synthea-export", {p.id: p for p in exported}

    fixture = _from_fixture()
    if not fixture:
        raise FileNotFoundError(
            f"No synthetic patients: put a Synthea CSV export in {CSV_DIR} or "
            f"restore {FIXTURE_FILE}."
        )
    return "fixture", {p.id: p for p in fixture}


def reload() -> None:
    """Drop the cache after dropping in an export or editing the fixture."""
    patients.cache_clear()
