"""The patient agent must be able to finish an intake, and must not embellish.

Two things are worth failing loudly on. A record that cannot answer a required
field stalls its run until the planner's question ceiling ends it, which reads
as a broken pipeline rather than a missing fixture. And an answer that claims
something the record does not contain would put a statement in a clinical
record the patient never made — the same rule the intake planner enforces on
denials, applied at the source.

The rest of the simulation is the browser calling public endpoints, so there is
nothing here about it.
"""

from services import patient_agent, synthea
from services.hospital_config import required_intake_fields


def load():
    synthea.reload()
    _, roster = synthea.patients()
    return list(roster.values())


def test_every_record_answers_every_required_field():
    required = set(required_intake_fields())
    for patient in load():
        answered = {
            field for field, text in patient_agent.answers_for(patient).items() if text
        }
        missing = required - answered
        assert not missing, f"{patient.id} cannot answer {sorted(missing)}"


def test_answers_come_from_the_record_only():
    for patient in load():
        answers = patient_agent.answers_for(patient)
        # An empty list is a denial, never silence and never an invention.
        if not patient.allergies:
            assert answers["allergy"].lower().startswith("no")
        else:
            assert patient.allergies[0].description in answers["allergy"]
        if not patient.medications:
            assert answers["medication"].lower().startswith("no")
        else:
            assert patient.medications[0].description in answers["medication"]
        if not patient.conditions:
            assert answers["history"].lower().startswith("no")
        else:
            assert patient.conditions[0].description in answers["history"]


def test_next_fact_follows_the_field_being_asked():
    patient = load()[0]
    field, fact = patient_agent.next_fact(patient, ["duration", "allergy"])
    assert field == "duration"
    assert fact == patient_agent.answers_for(patient)["duration"]

    # A field the record cannot answer must not produce a clinical claim.
    field, fact = patient_agent.next_fact(patient, ["insurance_number"])
    assert field == "insurance_number"
    assert fact == patient_agent.NO_ANSWER
    assert patient_agent.next_fact(patient, []) == (None, patient_agent.NO_ANSWER)


def test_a_reply_that_drops_the_fact_is_rejected():
    """"Do you take any medication?" -> "Yes." is fluent and useless.

    The model answered in character and told the extractor nothing, so the
    field never filled and intake asked again. Anything that carries the
    content through, however reworded, is kept.
    """
    fact = "I take Amlodipine 5 MG Oral Tablet."
    assert not patient_agent.states_the_fact("Yes.", fact)
    assert not patient_agent.states_the_fact("I do, yeah.", fact)
    assert patient_agent.states_the_fact("Yeah, I'm on amlodipine every morning.", fact)
    assert patient_agent.states_the_fact(fact, fact)

    denial = "No, I don't have any allergies."
    assert patient_agent.states_the_fact("No, no allergies at all.", denial)


def test_duration_reads_like_a_person():
    assert patient_agent.duration_phrase(0.25) == "about 6 hours"
    assert patient_agent.duration_phrase(2) == "about 2 days"
    assert patient_agent.duration_phrase(21) == "about 3 weeks"
    assert patient_agent.duration_phrase(90) == "about 3 months"


def test_clinical_qualifiers_are_stripped():
    """"Asthma (disorder)" is how Synthea writes it, not how a patient says it."""
    assert synthea.clean("Asthma (disorder)") == "Asthma"
    assert synthea.clean("Chest pain") == "Chest pain"
