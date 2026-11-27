"""What finalisation writes to the hospital chart's problem list: only the Past history the
doctor signed, never raw intake history facts."""

from app.services.hms.intake_sync import signed_problems


def test_problems_are_the_signed_past_history_lines():
    notes = ("Presenting complaints:\nUrinary frequency x 5 days\n\nPast history:\nAsthma\nHypertension.\n\n"
             "Allergies:\nSulfa drugs (rash)\n\nExamination:\nAfebrile")
    assert signed_problems(notes) == ["Asthma", "Hypertension"]


def test_nil_and_missing_past_history_write_nothing():
    assert signed_problems("Past history:\nNil significant\n\nExamination:\nNAD") == []
    assert signed_problems("Complaint and history:\nlast period was 2 weeks ago") == []
