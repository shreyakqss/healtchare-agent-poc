"""The simulated patient's side of the demo, and nothing more.

Two endpoints: the Synthea records available to run, and one turn of a patient
agent's speech. That is the whole of the backend's involvement in the
simulation. Everything else a simulated patient does — starting a session,
consenting, sending turns, pre-screening, review, notes, finalisation — is the
browser calling the same public endpoints the patient portal and staff
dashboard call.

Like `api/voice.py`, this imports no agent, no graph and no workflow, so there
is no path by which a simulated patient can triage, route or answer anything. A
simulated case is an ordinary case; the only trace of the simulation is
`demographics.simulated`, which the UI sets and no backend code branches on.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import patient_agent, synthea

router = APIRouter(prefix="/simulation", tags=["simulation"])


class CodedEntry(BaseModel):
    code: str
    description: str


class PatientProfile(BaseModel):
    """A Synthea record, as the simulation UI needs it.

    `answers` is included so the UI can show what the record contains beside
    what the extractor recovered from the conversation — the record is the
    ground truth of a run, and being able to compare the two is most of what
    makes the demo worth watching.
    """

    id: str
    name: str
    age: int
    gender: str
    headline: str
    expectation: str
    style: str
    opening: str
    reason: str
    duration_days: float
    conditions: list[CodedEntry]
    medications: list[CodedEntry]
    allergies: list[CodedEntry]
    answers: dict[str, str]


class PatientRoster(BaseModel):
    #: "synthea-export" when a real export is loaded, "fixture" otherwise.
    source: Literal["synthea-export", "fixture"]
    patients: list[PatientProfile]


class PatientReplyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    #: What intake still needs, straight from the last MessageResponse. Intake
    #: always asks about the first one, so that is the fact to state.
    missing_fields: list[str] = Field(default_factory=list)


class PatientReplyResponse(BaseModel):
    content: str
    field: str | None
    source: Literal["llm", "script"]


def _profile(patient: synthea.SyntheaPatient) -> PatientProfile:
    coded = lambda entries: [  # noqa: E731 - one shape, three call sites
        CodedEntry(code=entry.code, description=entry.description) for entry in entries
    ]
    return PatientProfile(
        id=patient.id,
        name=patient.name,
        age=patient.age,
        gender=patient.gender,
        headline=patient.headline or patient.reason,
        expectation=patient.expectation,
        style=patient.style,
        opening=patient.opening or f"I'm here about {patient.reason.lower()}.",
        reason=patient.reason,
        duration_days=round(patient.duration_days, 2),
        conditions=coded(patient.conditions),
        medications=coded(patient.medications),
        allergies=coded(patient.allergies),
        answers=patient_agent.answers_for(patient),
    )


def _roster() -> tuple[str, dict[str, synthea.SyntheaPatient]]:
    try:
        return synthea.patients()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/patients", response_model=PatientRoster)
def list_patients():
    """The synthetic patients the simulation can run. Synthea records only."""
    source, roster = _roster()
    return PatientRoster(
        source=source, patients=[_profile(p) for p in roster.values()]
    )


@router.post("/patients/{profile_id}/reply", response_model=PatientReplyResponse)
async def patient_reply(profile_id: str, payload: PatientReplyRequest):
    """One turn of patient speech, grounded in that patient's record."""
    _, roster = _roster()
    patient = roster.get(profile_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"No such patient: {profile_id}")

    turn = await patient_agent.reply(patient, payload.question, payload.missing_fields)
    return PatientReplyResponse(
        content=turn.content, field=turn.field, source=turn.source
    )
