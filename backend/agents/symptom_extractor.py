"""Symptom / History Extractor — patient answers into structured facts.

Every row written here carries `source_turn`, so a clinician can trace any fact
back to the exact sentence the patient said. Reviewer edits later go to
ClinicalReview.edits; these rows are the original patient statement and are
never overwritten.
"""

import logging
from sqlalchemy.orm import Session
from agents.question_planner import DECLINED, NONE_REPORTED, NOT_CAPTURED
from models import AllergyMedication, PatientCase, PatientFact
from schemas.agent_outputs import ExtractedFact, ExtractionResult, json_schema
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

# Fact kind -> the key the staff surfaces read off the case header. Mirrored
# there as they are extracted, because a queue row that says "Synthetic
# patient" for someone who gave their name three turns ago is the feature
# looking broken exactly where staff look. The fact rows remain the record of
# what was said; this is a copy for display, and the first value stated wins so
# a demographics fixture supplied at session start is never overwritten.
DEMOGRAPHIC_KEYS = {"name": "name", "age": "age", "gender": "sex"}

# A single fact is one clause of what the patient said. Anything longer is the
# model narrating instead of extracting, and it lands in the clinician's view.
MAX_FACT_CHARS = 220

# A bare negation is not a fact. The model tags "No" as whatever field was just
# asked about, which files "history: None" beside the denial the planner has
# already recorded properly. The denial belongs in the record; this echo of it
# does not.
EMPTY_ANSWERS = {"no", "none", "nope", "nothing", "nil", "n/a", "na", "-", "n"}


def is_empty_answer(value: str) -> bool:
    """Is this just the patient saying no, rather than a fact?"""
    return value.strip().strip(".,!").lower() in EMPTY_ANSWERS


PLACEHOLDER_ANSWERS = frozenset({NONE_REPORTED, DECLINED, NOT_CAPTURED})


def merge_demographics(current: dict, stated: list[tuple[str, str]]) -> dict:
    """Fold name/age/gender facts into the case's demographics.

    First value stated wins, so a fixture supplied when the session opened is
    never overwritten by a later extraction. Placeholder answers are skipped:
    intake writes one when a field was closed by a denial or a decline, and
    "Declined to answer" is not a name.
    """
    merged = dict(current)
    for kind, value in stated:
        value = (value or "").strip()
        if value and value not in PLACEHOLDER_ANSWERS and kind in DEMOGRAPHIC_KEYS:
            merged.setdefault(DEMOGRAPHIC_KEYS[kind], value)
    return merged


def sync_demographics(db: Session, case_id) -> dict:
    """Copy what intake collected onto the case, for the queue and case header."""
    case = db.get(PatientCase, case_id)
    if case is None:
        return {}

    facts = (
        db.query(PatientFact)
        .filter(PatientFact.case_id == case_id, PatientFact.kind.in_(DEMOGRAPHIC_KEYS))
        .order_by(PatientFact.source_turn)
        .all()
    )
    current = dict(case.demographics_fixture or {})
    updated = merge_demographics(current, [(f.kind, f.value) for f in facts])

    if updated != current:
        # Reassigned rather than mutated: SQLAlchemy does not track in-place
        # edits to a JSON column.
        case.demographics_fixture = updated
        db.commit()
    return updated

SYSTEM = """You extract structured information from what a patient said during intake.

Return only what the patient actually stated. Do not infer, expand, diagnose, or \
add clinical interpretation. If they did not mention something, leave it out.

Fact kinds:
- reason_for_visit: why they are seeking care
- symptom: a symptom they report
- duration: how long something has lasted (keep their wording, e.g. "about 3 weeks")
- history: a past or ongoing medical condition
- contact_preference: how they want to be contacted
- name: the patient's own name
- age: their age in years, as they said it
- gender: their gender, as they said it

Rules for the `value` field:
- Copy the patient's own words for that one item. Keep it under 15 words.
- Never explain your reasoning, never add caveats, never describe what is unknown.
  If something was not stated, simply omit that fact.

If the patient names a condition they live with (for example diabetes, asthma,
hypertension), record it as a `history` fact — even when they mention it in the
same breath as the medication they take for it. The medication also goes in
allergies_medications; the condition still belongs in facts.

One sentence usually carries SEVERAL facts. Split it. A patient who describes a
problem has told you the reason for the visit, the symptom, and often how long
it has lasted, all at once — emit one fact for each.

Example. The patient said: "Hi, I want to see a doctor. I've been having some
chest pain since this morning."
{"facts": [
  {"kind": "reason_for_visit", "value": "chest pain", "confidence": 1.0},
  {"kind": "symptom", "value": "chest pain", "confidence": 1.0},
  {"kind": "duration", "value": "since this morning", "confidence": 1.0}
], "allergies_medications": []}

Note that "chest pain" appears twice on purpose: it is both why they came and
the symptom itself. Never emit only reason_for_visit for a sentence like that.

Every medicine the patient names goes in allergies_medications, and so does
every allergy — including when naming it is the whole of what they said.

One introduction usually carries name, age and gender at once. Split it, and
emit only the ones they actually said.

Example. The patient said: "I'm Dev Sharma, I'm 34, male."
{"facts": [
  {"kind": "name", "value": "Dev Sharma", "confidence": 1.0},
  {"kind": "age", "value": "34", "confidence": 1.0},
  {"kind": "gender", "value": "male", "confidence": 1.0}
], "allergies_medications": []}

Example. The patient said: "I have asthma. I take a salbutamol inhaler twice a
day, and I'm allergic to penicillin."
{"facts": [
  {"kind": "history", "value": "asthma", "confidence": 1.0}
], "allergies_medications": [
  {"kind": "medication", "name": "salbutamol inhaler", "reaction_or_dose": "twice a day"},
  {"kind": "allergy", "name": "penicillin", "reaction_or_dose": ""}
]}

A fact you leave out is one the assistant has to ask the patient about again."""


async def extract_facts(
    db: Session, case_id, message: str, turn_index: int
) -> dict[str, int]:
    """Persist facts and allergy/medication entries from one patient message."""
    if not message.strip():
        return {"facts": 0, "allergies_medications": 0}

    user = f'The patient said:\n"""\n{message.strip()}\n"""'

    try:
        raw = await llm.chat_json(SYSTEM, user, json_schema(ExtractionResult))
        result = ExtractionResult.model_validate(raw)
    except (LLMError, ValueError) as exc:
        # Losing structure is bad but losing the statement is worse — keep the
        # raw text as a fact so nothing the patient said disappears.
        logger.warning("Extraction failed on turn %s, storing raw text: %s", turn_index, exc)
        db.add(
            PatientFact(
                case_id=case_id,
                kind="symptom",
                value=message.strip(),
                source_turn=turn_index,
                confidence=0.3,
            )
        )
        db.commit()
        return {"facts": 1, "allergies_medications": 0}

    existing = {
        (f.kind, f.value.strip().lower())
        for f in db.query(PatientFact).filter(PatientFact.case_id == case_id).all()
    }
    existing_entries = {
        (e.kind, e.name.strip().lower())
        for e in db.query(AllergyMedication)
        .filter(AllergyMedication.case_id == case_id)
        .all()
    }

    facts = list(result.facts)

    # The opening statement *is* the reason for visit. Small models routinely
    # tag it as a symptom only, which leaves the planner asking "what brings you
    # in today?" forever with no way for the patient to satisfy it. Deciding
    # this in code rather than hoping the model tags it removes the whole loop.
    if turn_index == 0 and not any(f.kind == "reason_for_visit" for f in facts):
        if not any(k == "reason_for_visit" for k, _ in existing):
            facts.insert(
                0,
                ExtractedFact(
                    kind="reason_for_visit",
                    value=message.strip()[:MAX_FACT_CHARS],
                    confidence=0.9,
                ),
            )

    # Why the patient came is settled once, on the first thing they said.
    # Small models tag almost every later answer as another reason_for_visit —
    # the reported transcript collected four, including "no" — which buries the
    # real one in the clinician's view.
    has_reason = any(kind == "reason_for_visit" for kind, _ in existing)

    fact_count = 0
    for fact in facts:
        value = fact.value.strip()[:MAX_FACT_CHARS]
        if not value or is_empty_answer(value) or (fact.kind, value.lower()) in existing:
            continue
        if fact.kind == "reason_for_visit":
            if has_reason:
                continue
            has_reason = True
        db.add(
            PatientFact(
                case_id=case_id,
                kind=fact.kind,
                value=value,
                source_turn=turn_index,
                confidence=fact.confidence,
            )
        )
        existing.add((fact.kind, value.lower()))
        fact_count += 1

    entry_count = 0
    for entry in result.allergies_medications:
        name = entry.name.strip()
        if not name or (entry.kind, name.lower()) in existing_entries:
            continue
        db.add(
            AllergyMedication(
                case_id=case_id,
                kind=entry.kind,
                name=name,
                reaction_or_dose=entry.reaction_or_dose.strip() or None,
                source_turn=turn_index,
            )
        )
        existing_entries.add((entry.kind, name.lower()))
        entry_count += 1

    db.commit()

    if fact_count:
        sync_demographics(db, case_id)
    return {"facts": fact_count, "allergies_medications": entry_count}
