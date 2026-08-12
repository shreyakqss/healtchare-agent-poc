"""Tappable answers for the question intake just asked.

A patient on a phone should not have to type "male" or "about two weeks". Each
question can therefore come with a few one-tap answers, and this is where they
come from. Two sources, and which one is used is decided by the field, not by
the model:

* **Fixed lists** for anything with a bounded set of honest answers — gender,
  how to reach someone, how long something has lasted, and the "no, none of
  those" reply to the three questions that most often deserve it. No model is
  consulted, because there is nothing to decide.
* **The model**, for the open questions (what the symptom is like, and whatever
  a clinic has added to its required fields), where the useful shortcut depends
  entirely on what the patient just said.

**Suggestions are shortcuts for typing, never prompts about what might be
wrong.** The generated ones may only rephrase or elaborate something the
patient has *already* stated: offering "chest pain" to someone who never
mentioned it would be putting a symptom in their mouth, and a patient tapping
it would file a statement they never made. The prompt forbids it, the fixed
lists contain no clinical content at all, and the free-text box is always still
there — nothing here narrows what a patient can say.

The options never reach the workflow. Whatever is tapped becomes an ordinary
patient message on the ordinary endpoint, so the agents see a sentence like any
other.
"""

from __future__ import annotations

import logging

from schemas.agent_outputs import AnswerOptions, json_schema
from services.llm_client import LLMError, llm

logger = logging.getLogger(__name__)

# At most this many chips, and none longer than this. A long option is the
# model writing a sentence for the patient rather than saving them a tap.
MAX_OPTIONS = 4
MAX_OPTION_CHARS = 42

# Bounded questions answer themselves. The duration wording is deliberate:
# every one of these parses in `triage_engine.parse_duration_days`, so a tapped
# answer reaches the two-week rule as a real number rather than as text the
# engine has to give up on.
STATIC_OPTIONS: dict[str, list[str]] = {
    "gender": ["Male", "Female", "Other", "Prefer not to say"],
    "contact_preference": ["Phone", "Email", "Text message"],
    "duration": [
        "A few hours",
        "About a day",
        "A few days",
        "About a week",
        "About 2 weeks",
        "More than a month",
    ],
    # The denial is the answer worth one tap — it is also the one patients skip,
    # which is what made intake ask twice before `_settle_last_question` existed.
    "history": ["No medical conditions", "I'm not sure"],
    "medication": ["I'm not taking any medication", "I'm not sure"],
    "allergy": ["No known allergies", "I'm not sure"],
}

# Fields where the patient's own words are the only honest answer, so nothing
# is offered at all. Asked for options, the model invented names to tap ("John
# Smith", "Jane Doe") and offered age *bands* — and a tapped option is filed as
# the patient's own statement, so one tap would have put a false name in a
# clinical record. There is no bounded set of names; the free-text box is the
# right control and it was always there.
FREE_TEXT_ONLY = {"name", "age"}

# Which of these need something typed after the tap, and what to ask for. The
# UI reveals one input; the composed message is still a single patient turn.
FOLLOW_UP_PROMPTS: dict[str, dict[str, str]] = {
    "contact_preference": {
        "Phone": "Your phone number",
        "Text message": "Your mobile number",
        "Email": "Your email address",
    }
}

SYSTEM = """You write one-tap answer options for a patient using a medical clinic's \
intake chat. They save the patient typing. They are NOT medical suggestions.

Rules, in order of importance:
1. Never introduce a symptom, condition, diagnosis, medicine or allergy the \
patient has not already mentioned. Only rephrase or add detail to what they \
themselves said.
2. Never suggest what might be wrong, never suggest urgency, never suggest \
treatment.
3. Write each option in the patient's first person, as a natural reply to the \
question asked.
4. At most 4 options, at most 6 words each, all different from one another.
5. If the question cannot be answered with short set options, return an empty \
list. An empty list is a perfectly good answer.

Example. The patient has said "I have a mild rash on my forearm that itches".
The assistant asked: "Can you tell me more about the rash?"
{"options": ["It itches a lot", "It is spreading", "It feels sore", "It comes and goes"]}

Note that every option is about the rash the patient already reported. Adding \
"I also have a fever" would be inventing a symptom for them."""


def static_for(field: str | None) -> list[str]:
    return list(STATIC_OPTIONS.get(field or "", []))


def follow_up_for(field: str | None, option: str) -> str | None:
    """What to ask for after this option is tapped, if anything."""
    return FOLLOW_UP_PROMPTS.get(field or "", {}).get(option)


def _clean(options: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for option in options:
        text = " ".join((option or "").split()).strip(" .\"'")
        if not text or len(text) > MAX_OPTION_CHARS or text.lower() in seen:
            continue
        seen.add(text.lower())
        kept.append(text)
        if len(kept) == MAX_OPTIONS:
            break
    return kept


async def suggest(
    field: str | None, question: str, transcript: list[dict[str, str]]
) -> tuple[list[str], str]:
    """Options for this question, and where they came from.

    Returns `([], "none")` rather than raising: options are a convenience, and
    a patient who never sees a chip has lost nothing but a tap.
    """
    static = static_for(field)
    if static:
        return static, "static"

    # No field means this is not a question about one — the closing message,
    # for instance. Nothing to offer, and nothing to spend a model call on.
    if not field or field in FREE_TEXT_ONLY:
        return [], "none"

    said = [turn["content"] for turn in transcript if turn.get("role") == "patient"]
    if not said:
        # Nothing to ground an option in, and the first question is the one
        # where inventing a complaint would do the most harm.
        return [], "none"

    user = (
        "What the patient has said so far:\n"
        + "\n".join(f"- {content}" for content in said[-6:])
        + f"\n\nThe assistant just asked: {question}\n\n"
        "Write the one-tap options."
    )

    try:
        raw = await llm.chat_json(SYSTEM, user, json_schema(AnswerOptions), temperature=0.3)
        options = _clean(AnswerOptions.model_validate(raw).options)
    except (LLMError, ValueError) as exc:
        logger.warning("Answer options unavailable for %r: %s", field, exc)
        return [], "none"

    return options, "llm" if options else "none"
