"""Typed contracts for every LLM call.

Each model serves twice: as the JSON schema handed to Ollama's `format` field
(so decoding is constrained) and as the validator for what comes back. One
definition, no drift between the two.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FactKind = Literal[
    "reason_for_visit",
    "symptom",
    "duration",
    "history",
    "condition",
    "contact_preference",
    "demographic",
]


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic's JSON schema, prepared for constrained decoding.

    Two adjustments, both learned the hard way against llama3.1:8b:

    1. **$defs are inlined.** Ollama compiles the schema into a decoding
       grammar and $ref indirection is the flakiest part of that path.

    2. **Every property is marked required.** A field with a Python default is
       not `required` in Pydantic's schema, and a small model reads "optional"
       as "skip it" — it silently dropped the entire `facts` array and only
       returned allergies. The Pydantic defaults still apply on the way back in,
       so validation stays tolerant; this only forces the *decoder* to emit
       each key.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                merged = {**inline(defs.get(name, {}))}
                merged.update({k: v for k, v in node.items() if k != "$ref"})
                return merged
            resolved = {k: inline(v) for k, v in node.items()}
            if resolved.get("type") == "object" and "properties" in resolved:
                resolved["required"] = list(resolved["properties"])
            return resolved
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return inline(schema)


# --- question planner ------------------------------------------------------


class NextQuestion(BaseModel):
    complete: bool = Field(
        description="True when every required field has been collected."
    )
    question: str = Field(
        default="",
        description="The single next question to ask the patient. Empty when complete.",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Required fields still outstanding.",
    )
    reason: str = Field(
        default="",
        description="One sentence on why this question is being asked.",
    )


# --- symptom / history extractor -------------------------------------------


class ExtractedFact(BaseModel):
    kind: FactKind
    value: str = Field(description="The patient's statement, lightly normalised.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractedAllergyMedication(BaseModel):
    kind: Literal["allergy", "medication"]
    name: str
    reaction_or_dose: str = ""


class ExtractionResult(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)
    allergies_medications: list[ExtractedAllergyMedication] = Field(
        default_factory=list
    )


# --- summary agents --------------------------------------------------------


class PrescreeningSummary(BaseModel):
    chief_complaint: str
    reported_symptoms: list[str] = Field(default_factory=list)
    relevant_history: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    context_for_clinician: str = Field(
        description=(
            "Neutral summary of what the patient stated. Does not diagnose, "
            "suggest treatment, or restate the administrative priority."
        )
    )


class VisitSummary(BaseModel):
    visit_reason: str
    consultation_overview: str
    doctor_notes_summary: str
    follow_up_instructions: list[str] = Field(default_factory=list)
    administrative_notes: str = ""
