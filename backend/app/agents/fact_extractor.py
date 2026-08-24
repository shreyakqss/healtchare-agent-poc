"""Symptom / history extractor: one patient message -> structured facts.

Returns only what the patient stated. The worked examples matter: without them
small models collapse a whole sentence into a single reason_for_visit.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.llm import make_agent, run_structured
from app.agents.schemas import ExtractionResult

INSTRUCTIONS = [
    "You extract structured information from what a patient said during intake.",
    "Return only what the patient actually stated. Never infer, expand, diagnose or interpret.",
    "Fact kinds: reason_for_visit, symptom, duration (keep their wording), history (a past or ongoing "
    "condition), contact_preference, name, age, gender.",
    "Copy the patient's own words for each item; keep each value under 15 words; no caveats.",
    "A condition the patient lives with (diabetes, asthma, hypertension) is a `history` fact even "
    "when mentioned beside the medication taken for it.",
    "One sentence usually carries SEVERAL facts - split it. A described problem gives reason_for_visit, "
    "symptom and often duration at once.",
    'Example - "I want to see a doctor, I\'ve had chest pain since this morning" -> facts: '
    '[reason_for_visit "chest pain", symptom "chest pain", duration "since this morning"].',
    'Example - "I\'m Dev Sharma, 34, male" -> facts: [name "Dev Sharma", age "34", gender "male"].',
    'Example - "I have asthma, I take a salbutamol inhaler twice a day and I\'m allergic to penicillin" -> '
    'facts: [history "asthma"]; allergies_medications: [medication "salbutamol inhaler" (twice a day), '
    'allergy "penicillin"].',
    "Every medicine named goes in allergies_medications as a medication; every allergy as an allergy.",
    "A fact you leave out is one the assistant has to ask again.",
]


@lru_cache(maxsize=1)
def _agent():
    return make_agent(
        name="Fact Extractor",
        role="Turn a patient statement into typed intake facts",
        instructions=INSTRUCTIONS,
        output_schema=ExtractionResult,
    )


async def extract(message: str) -> ExtractionResult:
    prompt = f'The patient said:\n"""\n{message.strip()}\n"""'
    return await run_structured(_agent(), prompt, ExtractionResult)