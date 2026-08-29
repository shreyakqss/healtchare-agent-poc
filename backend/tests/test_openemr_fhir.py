"""Pure FHIR mapping helpers for the OpenEMR adapter (no I/O)."""

from datetime import date

from app.domain.demographics import age_from_birth_date, parse_fhir_date
from app.integrations.hms.openemr import fhir
from app.integrations.hms.schemas import PatientRegistration

DEPARTMENTS = [
    {"id": "general_medicine", "name": "General Medicine", "default": True,
     "specialty_codes": ["207R00000X"], "specialty_names": ["Internal Medicine"]},
    {"id": "cardiology", "name": "Cardiology",
     "specialty_codes": ["207RC0000X"], "specialty_names": ["Cardiovascular Disease"]},
    {"id": "ent", "name": "ENT", "specialty_codes": ["207Y00000X"], "specialty_names": ["Otolaryngology"]},
]


def test_age_from_birth_date_counts_completed_years():
    assert age_from_birth_date(date(1990, 6, 15), today=date(2026, 6, 14)) == 35
    assert age_from_birth_date(date(1990, 6, 15), today=date(2026, 6, 15)) == 36


def test_parse_fhir_date_tolerates_datetime_and_garbage():
    assert parse_fhir_date("1990-06-15T10:00:00Z") == date(1990, 6, 15)
    assert parse_fhir_date("not a date") is None
    assert parse_fhir_date(None) is None


def test_human_name_prefers_text_then_given_family():
    assert fhir.human_name({"name": [{"text": "Priya Rao"}]}) == "Priya Rao"
    assert fhir.human_name({"name": [{"given": ["Priya", "K"], "family": "Rao"}]}) == "Priya K Rao"
    assert fhir.human_name({}) == "Unknown"


def test_mrn_prefers_mr_typed_identifier():
    identifiers = [
        {"value": "internal-1"},
        {"type": {"coding": [{"code": "MR"}]}, "value": "MRN-77"},
    ]
    assert fhir.mrn_from_identifiers(identifiers) == "MRN-77"
    assert fhir.mrn_from_identifiers([{"value": "only"}]) == "only"
    assert fhir.mrn_from_identifiers(None) is None


def test_patient_from_resource_maps_flat_fields_including_address():
    resource = {
        "id": "abc", "birthDate": "1990-01-01", "gender": "female",
        "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "MRN-1"}],
        "name": [{"text": "Priya Rao"}],
        "telecom": [{"system": "phone", "value": "555"}, {"system": "email", "value": "p@example.test"}],
        "address": [{"use": "home", "line": ["12 Demo Road", "Flat 3"], "city": "Pune",
                     "state": "Maharashtra", "postalCode": "411001", "country": "India"}],
    }
    patient = fhir.patient_from_resource(resource, conditions=["Asthma"])
    assert patient.mrn == "MRN-1" and patient.name == "Priya Rao" and patient.sex == "female"
    assert patient.phone == "555" and patient.email == "p@example.test"
    assert patient.birth_date == date(1990, 1, 1) and patient.age > 30
    assert patient.conditions == ["Asthma"]
    assert patient.address.line1 == "12 Demo Road" and patient.address.line2 == "Flat 3"
    assert (patient.address.city, patient.address.state) == ("Pune", "Maharashtra")
    assert (patient.address.postal_code, patient.address.country) == ("411001", "India")


def test_patient_without_address_maps_to_none():
    assert fhir.patient_from_resource({"id": "x"}).address is None


def test_codeable_helpers_tolerate_openemrs_bare_string_codings():
    """OpenEMR emits `coding: ["207RC0000X"]` where FHIR specifies objects."""
    node = [{"coding": ["207RC0000X"], "text": "Cardiovascular Disease"}]
    assert fhir.codeable_codes(node) == ["207RC0000X"]
    assert fhir.codeable_texts(node) == ["Cardiovascular Disease"]
    assert fhir.codeable_text({"code": {"coding": [{"display": "Penicillin"}]}}, "code") == "Penicillin"


def test_role_specialties_reads_code_when_specialty_is_null():
    """OpenEMR 8.3 leaves `specialty` null and puts the taxonomy in `code[]`."""
    resource = {"specialty": None, "code": [{"coding": ["207R00000X"], "text": "Internal Medicine"},
                                            {"coding": ["207RC0000X"], "text": "Cardiovascular Disease"}]}
    codes, texts = fhir.role_specialties(resource)
    assert codes == ["207R00000X", "207RC0000X"]
    assert texts == ["Internal Medicine", "Cardiovascular Disease"]


def test_match_department_by_taxonomy_code():
    assert fhir.match_department(["207RC0000X"], [], DEPARTMENTS) == "cardiology"


def test_match_department_by_specialty_name_then_substring():
    assert fhir.match_department([], ["Cardiovascular Disease"], DEPARTMENTS) == "cardiology"
    assert fhir.match_department([], ["ENT"], DEPARTMENTS) == "ent"  # substring on the department name


def test_specific_specialty_beats_the_generic_default_department():
    """OpenEMR tacks a generic specialty onto every role; the specific one must win."""
    codes = ["207R00000X", "207RC0000X"]
    texts = ["Internal Medicine", "Cardiovascular Disease"]
    assert fhir.match_department(codes, texts, DEPARTMENTS) == "cardiology"


def test_generic_specialty_alone_lands_in_the_default_department():
    assert fhir.match_department(["207R00000X"], ["Internal Medicine"], DEPARTMENTS) == "general_medicine"


def test_unmatched_specialty_is_unknown():
    assert fhir.match_department(["999X"], ["Astrophysics"], DEPARTMENTS) == fhir.UNKNOWN_DEPARTMENT
    assert fhir.match_department([], [], DEPARTMENTS) == fhir.UNKNOWN_DEPARTMENT


def test_roles_by_practitioner_merges_roles_and_unions_days():
    roles = [
        {"practitioner": {"reference": "Practitioner/p1"}, "code": [{"coding": ["207R00000X"], "text": "Internal Medicine"}],
         "availableTime": [{"daysOfWeek": ["mon", "wed"]}]},
        {"practitioner": {"reference": "Practitioner/p1"}, "code": [{"coding": ["207RC0000X"], "text": "Cardiovascular Disease"}],
         "availableTime": [{"daysOfWeek": ["wed", "fri"]}]},
        {"practitioner": {}, "code": [{"coding": ["207RC0000X"], "text": "Cardiovascular Disease"}]},
    ]
    out = fhir.roles_by_practitioner(roles, DEPARTMENTS)
    assert out == {"p1": {"department_id": "cardiology", "specialty": "Cardiovascular Disease",
                          "working_days": ["mon", "wed", "fri"]}}


def test_patient_body_splits_name_and_drops_extensions():
    registration = PatientRegistration(
        name="Nila K Shah", birth_date="1992-05-10", gender="nonbinary", phone="+91 9",
        address_line1="12 Demo Road", address_line2="Flat 3", city="Pune", state="MH",
        postal_code="411001", country="India", contact_preference="phone",
    )
    existing = {"resourceType": "Patient", "id": "p9", "extension": [{"url": "x"}], "telecom": [{"system": "fax", "value": "1"}]}
    body = fhir.patient_body(existing, registration)
    assert body["id"] == "p9" and "extension" not in body
    assert body["name"] == [{"use": "official", "given": ["Nila", "K"], "family": "Shah"}]
    assert body["gender"] == "unknown"  # non-FHIR gender is not written verbatim
    assert [t["system"] for t in body["telecom"]] == ["fax", "phone"]
    assert body["address"][0]["line"] == ["12 Demo Road", "Flat 3"]


def test_patient_body_round_trips_through_the_read_mapper():
    """What intake writes is what a later link pre-fills the form with."""
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", phone="+91 9", email="n@example.test",
        address_line1="12 Demo Road", city="Pune", state="MH", postal_code="411001",
        country="India", contact_preference="phone",
    )
    patient = fhir.patient_from_resource(fhir.patient_body(None, registration))
    assert patient.birth_date == date(1992, 5, 10) and patient.sex == "female"
    assert patient.phone == "+91 9" and patient.email == "n@example.test"
    assert patient.address.line1 == "12 Demo Road" and patient.address.postal_code == "411001"


def test_proposed_appointment_body_never_books():
    body = fhir.proposed_appointment_body(department_id="cardiology", reason="follow-up", patient_id="p1", practitioner_id="d1", slot_id="s1")
    assert body["status"] == "proposed"
    assert [p["actor"]["reference"] for p in body["participant"]] == ["Patient/p1", "Practitioner/d1"]
    assert body["slot"] == [{"reference": "Slot/s1"}]
    minimal = fhir.proposed_appointment_body(department_id="x", reason="r", patient_id=None, practitioner_id=None, slot_id=None)
    assert minimal["participant"] == [{"status": "needs-action"}]
