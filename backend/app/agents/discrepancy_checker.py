"""Discrepancy checker: patient-stated facts vs. uploaded document text / HMS records.

Flags factual mismatches only - never diagnoses, never infers clinical significance,
never suggests treatment. Same "extraction not interpretation" spirit as
`fact_extractor.py`. Output is clinician-facing only; it must never reach
`triage_engine.evaluate()`.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.llm import make_agent, run_structured
from app.agents.schemas import DiscrepancyResult

INSTRUCTIONS = [
    "You compare what a patient stated during intake against uploaded document text and HMS "
    "(hospital system) records for the same case, and flag factual mismatches only.",
    "You NEVER diagnose, infer clinical significance, suggest treatment, or offer opinions. You "
    "only report that two stated facts disagree.",
    "A discrepancy is a plain factual contradiction: the patient said one thing, and a document or "
    "HMS record says another. Example - patient says 'no medications' but a document lists one. "
    "Example - patient says 'symptoms for 2 days' but a referral letter says '3 weeks'.",
    "Do not flag things that are merely absent from one source, only ones that actively contradict "
    "each other. Do not flag paraphrases or trivial wording differences.",
    "For each discrepancy: quote the patient's own words for `patient_stated`, quote or closely "
    "paraphrase the document/HMS text for `document_or_hms_says`, set `source_kind` to 'document' or "
    "'hms', and set `attachment_id` to the id of the document if source_kind is 'document' (else leave it null).",
    "Set `severity` to 'review' when the mismatch could matter for care (e.g. medications, allergies, "
    "duration/severity of the presenting problem); use 'info' for minor administrative mismatches.",
    "If resolving the mismatch would clearly benefit from one more specific document from the patient "
    "(e.g. a current prescription list), name its kind in `requested_document_kind`; otherwise leave it null.",
    "If nothing contradicts, return an empty list. Do not invent discrepancies to have something to report.",
]


@lru_cache(maxsize=1)
def _agent():
    return make_agent(
        name="Discrepancy Checker",
        role="Flag factual mismatches between what a patient stated and what documents/HMS records say",
        instructions=INSTRUCTIONS,
        output_schema=DiscrepancyResult,
    )


async def check(prompt: str) -> DiscrepancyResult:
    """`prompt` should already lay out patient-stated facts vs. document/HMS text for the caller's case."""
    return await run_structured(_agent(), prompt, DiscrepancyResult)
