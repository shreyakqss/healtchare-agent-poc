"""The patient agent — a Synthea record, talking.

Two halves, deliberately separated:

* **The record decides what is true.** `answers_for()` turns a
  `SyntheaPatient` into the sentence that patient would say for each intake
  field. Conditions, medications, allergies, the reason for the visit and how
  long it has gone on all come straight out of the record, so the patient
  cannot report a symptom or a medicine Synthea never gave them.
* **The model decides how it is said.** `reply()` asks the LLM to say that
  sentence in the patient's own words, so three runs of one profile do not read
  identically and the extractor has real language to work on rather than a
  fixture it could match verbatim.

If the model is unavailable the derived sentence is sent as-is — the same
degrade-don't-block rule every agent in `agents/` follows. What is never
allowed is the reverse: the model inventing clinical content the record does
not contain, which is why it is given one fact and told to state it.

This is not a healthcare agent. It imports no workflow, no graph and no other
agent; it is the simulated person on the other side of the intake chat, and
everything it produces enters the system through the ordinary patient API.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from typing import Literal

from services.llm_client import LLMError, llm
from services.synthea import SyntheaPatient

logger = logging.getLogger(__name__)

# Said when the clinic asks for a field the record cannot answer — a hospital
# can require anything in `required_intake_fields`. It closes the question
# honestly (intake files it as "answered, see transcript") instead of inventing
# a clinical statement, and it never reads as a denial the patient did not make.
NO_ANSWER = "I'm not sure about that, sorry."

SYSTEM = """You are role-playing a patient in a medical clinic's text-based intake chat.

You are {name}, {age}, {gender}. Manner: {style}.

Reply as the patient, in the first person, in one or two short sentences. Plain \
spoken language — no lists, no formatting, no stage directions.

The single most important rule: your reply must state this fact, in your own \
words — "{fact}"

Never invent symptoms, conditions, medicines or allergies you were not given. \
Never ask the clinic questions. Never play the assistant. Reply with the \
patient's words and nothing else."""

GENDER_WORD = {"M": "male", "F": "female"}


@dataclass
class PatientTurn:
    content: str
    field: str | None
    #: Whether the persona wrote this or the derived sentence was sent as-is.
    #: Surfaced in the simulation UI so a degraded model is visible, not silent.
    source: Literal["llm", "script"]


def duration_phrase(days: float) -> str:
    """How a person says an elapsed time. Synthea records a timestamp."""
    if days < 1:
        hours = max(1, round(days * 24))
        return f"about {hours} hour{'s' if hours != 1 else ''}"
    if days < 14:
        whole = max(1, round(days))
        return f"about {whole} day{'s' if whole != 1 else ''}"
    if days < 60:
        return f"about {round(days / 7)} weeks"
    return f"about {round(days / 30)} months"


def _listed(entries) -> str:
    names = [entry.description for entry in entries if entry.description]
    if len(names) <= 1:
        return names[0] if names else ""
    return f"{', '.join(names[:-1])} and {names[-1]}"


def answers_for(patient: SyntheaPatient) -> dict[str, str]:
    """What this record says, one sentence per intake field.

    Empty entries are answered with a plain "No, ..." rather than silence: a
    patient with no allergies says so, and intake records that denial. Anything
    vaguer would read to the planner as a question never answered, and it would
    ask again.
    """
    reason = patient.reason or "something I'd like checked"
    conditions = _listed(patient.conditions)
    medications = _listed(patient.medications)
    allergies = _listed(patient.allergies)

    return {
        # Synthea's patients.csv columns, said out loud.
        "name": f"My name is {patient.name}.",
        "age": f"I'm {patient.age}.",
        "gender": f"I'm {GENDER_WORD.get(patient.gender, patient.gender or 'not saying')}.",
        "reason_for_visit": f"I'm here because of {reason.lower()}.",
        "symptom": f"It's {patient.symptom}." if patient.symptom else f"It's {reason.lower()}.",
        "duration": f"It started {duration_phrase(patient.duration_days)} ago.",
        "history": (
            f"I have {conditions}."
            if conditions
            else "No, I don't have any medical conditions."
        ),
        "medication": (
            f"I take {medications}."
            if medications
            else "No, I don't take any medication."
        ),
        "allergy": (
            f"I'm allergic to {allergies}."
            if allergies
            else "No, I don't have any allergies."
        ),
        "contact_preference": f"Please contact me by {patient.contact_preference}.",
    }


def states_the_fact(spoken: str, fact: str) -> bool:
    """Did the reply actually carry the record's content?

    A small model asked "do you take any medication?" will happily answer
    "Yes." — fluent, in character, and useless: the extractor gets nothing, the
    field never fills, and intake asks again until it gives up. So the reply has
    to contain something of the fact it was given. Any one substantial word
    counts, because rephrasing is the whole reason the model is here; what is
    rejected is a reply that dropped the content entirely.
    """
    words = {word for word in re.findall(r"[a-z0-9]{4,}", fact.lower())}
    if not words:
        return True
    return any(word in spoken.lower() for word in words)


def next_fact(patient: SyntheaPatient, missing_fields: list[str]) -> tuple[str | None, str]:
    """The field being asked about, and what this record says about it.

    Intake asks about the first outstanding field, so that is the one to
    answer. Preferring a field the record can actually answer keeps a hospital
    that requires something unexpected from derailing the run on question one.
    """
    answers = answers_for(patient)
    field = next(
        (name for name in missing_fields if name in answers),
        missing_fields[0] if missing_fields else None,
    )
    return field, answers.get(field or "", NO_ANSWER)


async def reply(
    patient: SyntheaPatient, question: str, missing_fields: list[str]
) -> PatientTurn:
    """What this patient says next."""
    field, fact = next_fact(patient, missing_fields)

    try:
        spoken = await llm.chat_text(
            SYSTEM.format(
                name=patient.name,
                age=patient.age,
                gender=GENDER_WORD.get(patient.gender, "patient"),
                style=patient.style,
                fact=fact,
            ),
            f"The intake assistant asked you: {question}",
            # Some spread, or every patient sounds like the same person.
            temperature=random.uniform(0.5, 0.9),
        )
    except LLMError as exc:
        logger.warning("Patient agent %s fell back to its record: %s", patient.id, exc)
        return PatientTurn(content=fact, field=field, source="script")

    spoken = spoken.strip().strip('"')
    # Empty, a monologue rather than an answer, or an answer that dropped the
    # fact: send the record's own sentence, which is never wrong.
    if not spoken or len(spoken) > 400 or not states_the_fact(spoken, fact):
        return PatientTurn(content=fact, field=field, source="script")
    return PatientTurn(content=spoken, field=field, source="llm")
