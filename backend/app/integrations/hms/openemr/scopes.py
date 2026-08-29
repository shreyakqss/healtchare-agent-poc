"""The OAuth2 scopes the OpenEMR adapter needs - one place, shared by settings and the
registration script.

OpenEMR 8.3 exposes two APIs under one token: FHIR R4 (`/apis/default/fhir`, read-oriented -
on 8.3 only `Patient` accepts writes) and the standard REST API (`/apis/default/api`, where
clinical writes live). Scopes are fixed when the client is registered, so both families are
requested up front. `.read`/`.write` are the only suffixes OpenEMR's OAuth server accepts.
"""

FHIR_SCOPES = (
    "api:fhir",
    "user/Patient.read", "user/Patient.write",
    "user/Practitioner.read", "user/PractitionerRole.read",
    "user/Appointment.read",
    "user/DocumentReference.read",
    # No user/MedicationStatement.* - OpenEMR 8.3's OAuth server rejects it as unknown
    # (confirmed live); current medications are read through the standard API instead.
    "user/Condition.read", "user/AllergyIntolerance.read",
    "user/Encounter.read",
)

STANDARD_API_SCOPES = (
    "api:oemr",
    "user/patient.read", "user/patient.write",
    "user/practitioner.read", "user/facility.read", "user/list.read",
    "user/medical_problem.read", "user/medical_problem.write",
    "user/allergy.read", "user/allergy.write",
    "user/medication.read", "user/medication.write",
    "user/document.read", "user/document.write",
    # The visit itself: an encounter is the chart container a consultation note hangs off,
    # and the note is a SOAP form on it - OpenEMR scopes the form separately.
    "user/encounter.read", "user/encounter.write",
    "user/soap_note.read", "user/soap_note.write",
    # Read-only on purpose. Creating an OpenEMR appointment puts it on the calendar, which is
    # a booking - CareFlow files an appointment *request* on the chart instead.
    "user/appointment.read",
)

DEFAULT_SCOPES = " ".join(("openid", "offline_access", *FHIR_SCOPES, *STANDARD_API_SCOPES))
