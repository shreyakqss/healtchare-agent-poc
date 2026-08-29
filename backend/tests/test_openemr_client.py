"""Unit tests for the OpenEMR FHIR adapter. No live OpenEMR - httpx calls are mocked."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.core.errors import HMSRejected
from app.integrations.hms.openemr import FhirHMS
from app.integrations.hms.schemas import AppointmentRequest, PatientRegistration

REQUEST = "app.integrations.hms.openemr.client.httpx.request"
REST_REQUEST = "app.integrations.hms.openemr.rest.httpx.request"
TOKEN_POST = "app.integrations.hms.openemr.auth.httpx.post"
JWKS_GET = "app.integrations.hms.openemr.auth.httpx.get"
# `id` is deliberately NOT the pid: OpenEMR's patient row carries both, and they diverge once
# any record is deleted. Every patient-scoped endpoint keys on `pid`.
PATIENT_ROW = {"validationErrors": [], "internalErrors": [],
               "data": {"id": 77, "pid": 9, "uuid": "abc123", "pubpid": "9"}}


def _resp(json_body: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_body, request=httpx.Request("GET", "http://x"))


def _client(**overrides) -> FhirHMS:
    kwargs = dict(
        base_url="http://localhost:8300",
        fhir_path="/apis/default/fhir",
        token_url="http://localhost:8300/oauth2/default/token",
        client_id="cid",
        client_secret="csecret",
        scopes="system/Patient.read",
    )
    kwargs.update(overrides)
    return FhirHMS(**kwargs)


def _with_token(hms: FhirHMS):
    return patch.object(hms._tokens, "access_token", return_value="tok")


def _router(routes: dict[str, dict]):
    """fake httpx.request keyed by URL suffix, optionally method-prefixed ('POST /Appointment').
    A callable value receives the request kwargs and returns the response."""

    def fake_request(method, url, **kwargs):
        for key, body in routes.items():
            wanted_method, _, suffix = key.rpartition(" ")
            if url.endswith(suffix) and (not wanted_method or wanted_method == method):
                return body(kwargs) if callable(body) else _resp(body)
        raise AssertionError(f"unexpected call {method} {url}")

    return fake_request


PATIENT = {
    "resourceType": "Patient", "id": "abc123",
    "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "MRN-1"}],
    "name": [{"text": "Priya Rao"}], "gender": "female", "birthDate": "1990-01-01",
    "telecom": [{"system": "phone", "value": "555-1234"}],
}
PATIENT_BUNDLE = {"entry": [{"resource": PATIENT}]}
EMPTY = {"entry": []}


# --- auth --------------------------------------------------------------------

def test_token_fetch_and_cache():
    hms = _client()
    with patch(TOKEN_POST) as mock_post:
        mock_post.return_value = _resp({"access_token": "tok-1", "expires_in": 3600})
        assert hms._tokens.access_token() == "tok-1"
        assert hms._tokens.access_token() == "tok-1"
    mock_post.assert_called_once()  # second call served from cache
    assert mock_post.call_args.kwargs["data"]["grant_type"] == "client_credentials"


def test_password_grant_used_when_service_user_configured():
    hms = _client(username="svc", password="pw")
    with patch(TOKEN_POST) as mock_post:
        mock_post.return_value = _resp({"access_token": "tok-1", "expires_in": 3600})
        hms._tokens.access_token()
    form = mock_post.call_args.kwargs["data"]
    assert form["grant_type"] == "password" and form["username"] == "svc" and form["user_role"] == "users"


def test_short_lived_token_is_never_cached_past_its_expiry():
    hms = _client()
    with patch(TOKEN_POST, return_value=_resp({"access_token": "tok-1", "expires_in": 5})):
        with patch("app.integrations.hms.openemr.auth.time.monotonic", return_value=100):
            hms._tokens.access_token()
    assert hms._tokens._expiry == 101


def test_request_retries_once_on_401_with_fresh_token():
    hms = _client()
    responses = [_resp({}, status_code=401), _resp(PATIENT_BUNDLE)]
    with patch(REQUEST, side_effect=lambda *a, **k: responses.pop(0)) as mock_req:
        with patch.object(hms._tokens, "access_token", side_effect=["stale", "fresh"]) as token:
            hms.search_patients("priya")
    assert mock_req.call_count == 2
    assert token.call_args_list[1].args == (True,)  # forced refresh on the retry


# --- read side ---------------------------------------------------------------

def test_search_patients_mapping():
    hms = _client()
    with patch(REQUEST, return_value=_resp(PATIENT_BUNDLE)), _with_token(hms):
        results = hms.search_patients("priya", limit=10)
    assert len(results) == 1
    p = results[0]
    assert (p.mrn, p.name, p.sex, p.phone) == ("MRN-1", "Priya Rao", "female", "555-1234")
    assert p.conditions == [] and p.medications == [] and p.allergies == []


def test_search_patients_falls_back_to_identifier_search():
    hms = _client()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs["params"])
        return _resp(EMPTY if "name" in kwargs["params"] else PATIENT_BUNDLE)

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        results = hms.search_patients("MRN-1")
    assert [p.mrn for p in results] == ["MRN-1"]
    assert calls[0]["name"] == "MRN-1" and calls[1]["identifier"] == "MRN-1"


def test_get_patient_mapping_includes_clinical_lists_and_last_visit():
    hms = _client()
    routes = {
        "/Patient": PATIENT_BUNDLE,
        "/Condition": {"entry": [{"resource": {"code": {"text": "Hypertension"}}}]},
        "/MedicationStatement": {"entry": [{"resource": {"medicationCodeableConcept": {"text": "Lisinopril"}}}]},
        "/AllergyIntolerance": {"entry": [{"resource": {"code": {"coding": [{"display": "Penicillin"}]}}}]},
        "/Encounter": {"entry": [{"resource": {"period": {"start": "2026-05-14T09:30:00+00:00"}}}]},
        # standard API: allergy titles unavailable here -> FHIR fallback above is used
        "/apis/default/api/patient/abc123/allergy": lambda kw: _resp({}, status_code=404),
        # ...but it does hold what FHIR omits: the country and the contact preference.
        "/apis/default/api/patient/abc123": {
            "validationErrors": [], "internalErrors": [],
            "data": {"id": 77, "pid": 9, "country_code": "India", "hipaa_voice": "YES", "hipaa_allowemail": "NO"},
        },
    }
    with patch(REQUEST, side_effect=_router(routes)), _with_token(hms):
        patient = hms.get_patient("MRN-1")
    assert patient.address.country == "India"
    assert patient.contact_preference == "phone"

    assert patient is not None
    assert patient.mrn == "MRN-1"
    assert patient.conditions == ["Hypertension"]
    assert patient.medications == ["Lisinopril"]
    assert patient.allergies == ["Penicillin"]
    assert str(patient.last_visit) == "2026-05-14"


def test_get_patient_prefers_standard_api_allergy_titles():
    hms = _client()
    routes = {
        "/apis/default/api/patient/abc123/allergy": {"validationErrors": [], "internalErrors": [], "data": [{"title": "penicillin (rash)"}]},
        "/Patient": PATIENT_BUNDLE,
        "/AllergyIntolerance": {"entry": [{"resource": {"code": {"text": "Unknown"}}}]},
    }

    def fake_request(method, url, **kwargs):
        try:
            return _router(routes)(method, url, **kwargs)
        except AssertionError:
            return _resp({}, status_code=404)  # every other list is empty

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        assert hms.get_patient("MRN-1").allergies == ["penicillin (rash)"]


def test_get_patient_tolerates_unscoped_clinical_resources():
    """A 403 on Condition/MedicationStatement/... (scope not granted) is not fatal."""
    hms = _client()

    def fake_request(method, url, **kwargs):
        if url.endswith("/Patient"):
            return _resp(PATIENT_BUNDLE)
        raise httpx.HTTPStatusError("forbidden", request=httpx.Request("GET", url), response=httpx.Response(403))

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        patient = hms.get_patient("MRN-1")
    assert patient is not None and patient.conditions == [] and patient.last_visit is None


def test_get_patient_not_found_returns_none():
    hms = _client()
    with patch(REQUEST, return_value=_resp(EMPTY)), _with_token(hms):
        assert hms.get_patient("nope") is None


def test_register_patient_creates_fhir_patient():
    hms = _client()
    created = {
        "resourceType": "Patient", "id": "pat-99", "name": [{"text": "Nila Shah"}],
        "birthDate": "1992-05-10", "gender": "female",
        "telecom": [{"system": "phone", "value": "+919999999999"}],
    }
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", phone="+919999999999",
        email="nila@example.test", address_line1="12 Demo Road", city="Pune", state="Maharashtra",
        postal_code="411001", country="India", contact_preference="text",
    )
    with patch(REQUEST, return_value=_resp(created)) as mock_req, _with_token(hms):
        patient = hms.register_patient(None, registration)
    create_call = mock_req.call_args_list[0]
    method, url = create_call.args[:2]
    body = create_call.kwargs["json"]
    assert method == "POST" and url.endswith("/Patient")
    assert body["birthDate"] == "1992-05-10"
    assert body["telecom"][0]["value"] == "+919999999999"
    assert patient.mrn == "pat-99"


def test_register_patient_rereads_record_when_create_returns_only_location():
    """OpenEMR answers POST Patient with a minimal body and the id in `Location`; the MRN
    (public identifier) only exists on the re-read resource."""
    hms = _client()
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", address_line1="1 Road",
        city="Pune", state="MH", postal_code="1", country="India", contact_preference="phone",
    )
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        if method == "POST":
            return httpx.Response(201, json={}, request=httpx.Request("POST", url), headers={"Location": f"{url}/new-99"})
        if method == "PUT":  # the standard-API demographics write, covered by its own test
            return _resp({"validationErrors": [], "internalErrors": [], "data": {"id": 7}})
        assert url.endswith("/Patient/new-99")
        return _resp({**PATIENT, "id": "new-99", "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "7"}]})

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        patient = hms.register_patient(None, registration)
    assert patient.mrn == "7"
    # create -> re-read for the MRN -> store what the FHIR write drops.
    assert [m for m, _ in calls] == ["POST", "GET", "PUT"]


def test_register_patient_stores_the_demographics_fhir_drops():
    """OpenEMR's FHIR Patient write silently discards the address country and has nowhere for
    a contact preference, so both go through the standard API instead - otherwise a returning
    patient re-enters them every visit."""
    hms = _client()
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", address_line1="1 Road",
        city="Pune", state="MH", postal_code="1", country="India", contact_preference="email",
    )
    writes: list[tuple[str, dict]] = []

    def fake_request(method, url, **kwargs):
        if "/apis/default/api/" in url:
            writes.append((url.split("/apis/default/api/", 1)[1], kwargs.get("json") or {}))
            return _resp({"validationErrors": [], "internalErrors": [], "data": {"id": 7}})
        return _resp(PATIENT)

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        hms.register_patient(None, registration)

    assert writes == [("patient/abc123", {"country_code": "India", "hipaa_voice": "NO", "hipaa_allowemail": "YES"})]


def test_register_patient_survives_a_failed_demographics_write():
    """The patient is registered by that point - losing country/preference must not lose the
    registration itself."""
    hms = _client()
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", address_line1="1 Road",
        city="Pune", state="MH", postal_code="1", country="India", contact_preference="email",
    )

    def fake_request(method, url, **kwargs):
        if "/apis/default/api/" in url:
            raise httpx.ConnectError("standard API down")
        return _resp(PATIENT)

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        assert hms.register_patient(None, registration).mrn == "MRN-1"


def test_register_patient_handles_openemr_pid_uuid_reply():
    """Live OpenEMR 8.3 answers POST Patient with {"pid": N, "uuid": "<fhir id>"}."""
    hms = _client()
    registration = PatientRegistration(
        name="Nila Shah", birth_date="1992-05-10", gender="female", address_line1="1 Road",
        city="Pune", state="MH", postal_code="1", country="India", contact_preference="phone",
    )

    def fake_request(method, url, **kwargs):
        if method == "POST":
            return httpx.Response(201, json={"pid": 6, "uuid": "a299-uuid"}, request=httpx.Request("POST", url))
        assert url.endswith("/Patient/a299-uuid")
        return _resp({**PATIENT, "id": "a299-uuid", "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "6"}]})

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        assert hms.register_patient(None, registration).mrn == "6"


def test_find_patient_falls_back_to_resource_id_read():
    """A record with no public identifier is addressed by its FHIR id."""
    hms = _client()

    def fake_request(method, url, **kwargs):
        if url.endswith("/Patient/abc123"):
            return _resp(PATIENT)
        return _resp(EMPTY)  # identifier search misses; clinical lists are empty

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        patient = hms.get_patient("abc123")
    assert patient is not None and patient.name == "Priya Rao"


def test_get_patient_ignores_non_patient_body_on_direct_read():
    hms = _client()
    with patch(REQUEST, return_value=_resp({"resourceType": "OperationOutcome"})), _with_token(hms):
        assert hms.get_patient("ghost") is None


def test_available_slots_is_empty_when_install_has_no_slot_endpoint():
    hms = _client()
    with patch(REQUEST, side_effect=httpx.HTTPStatusError("nf", request=httpx.Request("GET", "http://x"), response=httpx.Response(404))):
        with _with_token(hms):
            assert hms.available_slots("cardiology", "p1") == []


def test_register_patient_updates_linked_record_with_put():
    hms = _client()
    registration = PatientRegistration(
        name="Priya Rao", birth_date="1990-01-01", gender="female", address_line1="1 Road",
        city="Pune", state="MH", postal_code="1", country="India", contact_preference="phone",
    )
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return _resp(PATIENT_BUNDLE if method == "GET" else PATIENT)

    with patch(REQUEST, side_effect=fake_request), _with_token(hms):
        hms.register_patient("MRN-1", registration)
    # A linked record is updated in place - never created a second time.
    assert ("PUT", "http://localhost:8300/apis/default/fhir/Patient/abc123") in calls
    assert not any(method == "POST" for method, _ in calls)


def test_list_documents_mapping():
    hms = _client()
    doc_bundle = {"entry": [{"resource": {
        "resourceType": "DocumentReference", "id": "doc-1", "type": {"text": "Lab report"},
        "date": "2026-01-18T00:00:00Z", "content": [{"attachment": {"contentType": "application/pdf"}}],
    }}]}
    with patch(REQUEST, side_effect=_router({"/Patient": PATIENT_BUNDLE, "/DocumentReference": doc_bundle})), _with_token(hms):
        docs = hms.list_documents("MRN-1")
    assert len(docs) == 1
    assert (docs[0].reference, docs[0].title, docs[0].content_type) == ("doc-1", "Lab report", "application/pdf")
    assert docs[0].created is not None


def test_list_documents_returns_empty_when_patient_not_found():
    hms = _client()
    with patch(REQUEST, return_value=_resp(EMPTY)), _with_token(hms):
        assert hms.list_documents("nope") == []


def test_get_document_content_refuses_other_patients_documents():
    hms = _client()
    document = {"id": "doc-1", "subject": {"reference": "Patient/someone-else"}, "content": [{"attachment": {"data": "aGk="}}]}
    with patch(REQUEST, side_effect=_router({"/Patient": PATIENT_BUNDLE, "/DocumentReference/doc-1": document})), _with_token(hms):
        with pytest.raises(PermissionError):
            hms.get_document_content("MRN-1", "doc-1")


def test_get_document_content_refuses_foreign_attachment_url_without_sending_token():
    hms = _client()
    document = {
        "id": "doc-1",
        "subject": {"reference": "Patient/abc123"},
        "content": [{"attachment": {"url": "http://attacker.invalid/steal", "contentType": "application/pdf"}}],
    }
    with patch(
        REQUEST,
        side_effect=_router({"/Patient": PATIENT_BUNDLE, "/DocumentReference/doc-1": document}),
    ) as request, _with_token(hms):
        with pytest.raises(HMSRejected):
            hms.get_document_content("MRN-1", "doc-1")
    assert request.call_count == 2


def test_get_document_content_refuses_malformed_attachment_url_without_sending_token():
    hms = _client()
    document = {
        "id": "doc-1",
        "subject": {"reference": "Patient/abc123"},
        "content": [{"attachment": {"url": "http://localhost:invalid/file"}}],
    }
    with patch(
        REQUEST,
        side_effect=_router({"/Patient": PATIENT_BUNDLE, "/DocumentReference/doc-1": document}),
    ) as request, _with_token(hms):
        with pytest.raises(HMSRejected):
            hms.get_document_content("MRN-1", "doc-1")
    assert request.call_count == 2


def test_list_practitioners_dedupes_by_id():
    """OpenEMR fans each practitioner out into duplicate bundle rows - dedupe by id."""
    hms = _client()
    bundle = {"entry": [
        {"resource": {"id": "p1", "name": [{"text": "Dr. A"}]}},
        {"resource": {"id": "p1", "name": [{"text": "Dr. A"}]}},
        {"resource": {"id": "p2", "name": [{"text": "Dr. B"}]}},
    ]}
    with patch(REQUEST, side_effect=_router({"/Practitioner": bundle, "/PractitionerRole": EMPTY})), _with_token(hms):
        out = hms.list_practitioners()
    assert {p.id for p in out} == {"p1", "p2"} and len(out) == 2


def test_list_practitioners_joins_practitioner_role_for_department_and_days():
    hms = _client()
    practitioners = {"entry": [
        {"resource": {"id": "p1", "name": [{"text": "Dr. A"}]}},
        {"resource": {"id": "p2", "name": [{"text": "Dr. B"}]}},
    ]}
    roles = {"entry": [
        {"resource": {"practitioner": {"reference": "Practitioner/p1"}, "specialty": [{"text": "Cardiology"}],
                      "availableTime": [{"daysOfWeek": ["mon", "wed"]}, {"daysOfWeek": ["fri"]}]}},
        {"resource": {"practitioner": {"reference": "Practitioner/p2"}, "specialty": [{"text": "Something Unmapped"}],
                      "availableTime": [{"daysOfWeek": ["tue"]}]}},
    ]}
    with patch(REQUEST, side_effect=_router({"/Practitioner": practitioners, "/PractitionerRole": roles})), _with_token(hms):
        with patch("app.services.hospital_config.departments", return_value=[{"id": "cardiology", "name": "Cardiology"}]):
            out = {p.id: p for p in hms.list_practitioners()}
    assert out["p1"].department_id == "cardiology" and out["p1"].working_days == ["mon", "wed", "fri"]
    assert out["p2"].department_id == "unknown" and out["p2"].working_days == ["tue"]


def test_status_counts_real_entries_and_caches():
    hms = _client(status_cache_seconds=60)
    practitioners = {"entry": [
        {"resource": {"id": "p1", "name": [{"text": "Dr. A"}]}},
        {"resource": {"id": "p1", "name": [{"text": "Dr. A"}]}},
        {"resource": {"id": "p2", "name": [{"text": "Dr. B"}]}},
    ]}
    routes = {"/Patient": {"entry": [{"resource": {"id": "pt1"}}]}, "/Practitioner": practitioners,
              "/PractitionerRole": EMPTY, "/Appointment": EMPTY}
    with patch(REQUEST, side_effect=_router(routes)) as mock_req, _with_token(hms):
        first = hms.status()
        second = hms.status()
    assert first.connected is True and first.patients == 1 and first.practitioners == 2 and first.pending_requests == 0
    assert second is first
    assert mock_req.call_count == 4  # cached: no second round-trip


def test_status_reports_disconnected_on_error():
    hms = _client(status_cache_seconds=0)
    with patch(REQUEST, side_effect=httpx.ConnectError("down")), _with_token(hms):
        status = hms.status()
    assert status.connected is False and status.patients == 0


# --- write side (standard API) ---------------------------------------------------

def _combined_router(calls: list):
    """One fake for both APIs (they share `httpx.request`): FHIR GETs find the patient,
    standard-API calls resolve the pid and record every write as ("api", method, path, kwargs)."""

    def fake_request(method, url, **kwargs):
        if "/apis/default/fhir/" in url:
            calls.append(("fhir", method, url.rsplit("/apis/default/fhir/", 1)[1], kwargs))
            assert method == "GET", f"unexpected FHIR write {method} {url}"
            return _resp(PATIENT_BUNDLE)
        path = url.split("/apis/default/api/", 1)[1]
        calls.append(("api", method, path, kwargs))
        if method == "GET" and path == "patient/abc123":
            return _resp(PATIENT_ROW)
        if path.endswith("/document"):
            return _resp(True)
        if path.endswith("/encounter"):
            return _resp({"validationErrors": [], "internalErrors": [], "data": {"eid": 12, "euuid": "enc-uuid"}})
        return _resp({"validationErrors": [], "internalErrors": [], "data": {"id": 1, "uuid": "row-uuid"}})

    return fake_request


def _api_writes(calls: list) -> list[tuple[str, dict]]:
    return [(path, kwargs) for api, method, path, kwargs in calls if api == "api" and method == "POST"]


def test_push_document_uploads_to_chart_and_returns_location_reference():
    hms = _client()
    calls = []
    with patch(REST_REQUEST, side_effect=_combined_router(calls)), _with_token(hms):
        ref = hms.push_document("MRN-1", "Visit Summary", b"clinician-approved text")
    assert ref == "openemr:patient/9/document/visit-summary.txt"
    upload = dict(_api_writes(calls))["patient/9/document"]
    assert upload["params"] == {"path": "/Documents"}
    assert upload["files"]["document"] == ("visit-summary.txt", b"clinician-approved text", "text/plain")


def test_request_appointment_files_a_request_note_and_never_books():
    hms = _client()
    calls = []
    req = AppointmentRequest(
        case_id="c1", patient_mrn="MRN-1", patient_name="Priya Rao", department_id="cardiology",
        practitioner_id="dr_rao", appointment_type_id="urgent_slot", priority="high", reason="follow-up",
    )
    with patch(REST_REQUEST, side_effect=_combined_router(calls)), _with_token(hms):
        result = hms.request_appointment(req)
    assert result.status == "requested" and result.reference.startswith("openemr:patient/9/document/careflow-appointment-request")
    writes = dict(_api_writes(calls))
    assert list(writes) == ["patient/9/document"]  # no calendar event, no FHIR Appointment (router asserts GET-only FHIR)
    filename, body, content_type = writes["patient/9/document"]["files"]["document"]
    assert (filename, content_type) == ("careflow-appointment-request.txt", "text/plain")  # plain text: OpenEMR declines sniffed JSON
    assert b"Status: requested - to be scheduled by staff" in body and b"Department: cardiology" in body


def test_sync_reviewed_intake_opens_an_encounter_with_the_clinicians_note():
    """The visit becomes an encounter with a SOAP note - that is what puts it in the patient's
    history and what `last_visit` reads. Every section comes from recorded content."""
    hms = _client()
    calls = []
    payload = {
        "facts": [{"kind": "reason_for_visit", "value": "Headache for three weeks", "source": "patient"}],
        "entries": [],
        "consultation_notes": [{"notes": "Tension-type pattern.", "prescription": "Paracetamol 500mg",
                                "follow_up_instructions": "Review in 2 weeks."}],
    }
    with patch(REST_REQUEST, side_effect=_combined_router(calls)), _with_token(hms):
        hms.sync_reviewed_intake("MRN-1", payload)

    writes = dict(_api_writes(calls))
    encounter = writes["patient/abc123/encounter"]["json"]
    assert encounter["reason"] == "Headache for three weeks" and encounter["class_code"] == "AMB"
    soap = writes["patient/9/encounter/12/soap_note"]["json"]
    assert soap["subjective"] == "Headache for three weeks"
    assert soap["assessment"] == "Tension-type pattern."
    assert soap["plan"] == "Paracetamol 500mg\nReview in 2 weeks."
    assert soap["objective"] == "Not recorded during intake."  # CareFlow collects no findings


def test_sync_reviewed_intake_survives_a_hospital_system_that_cannot_take_an_encounter():
    """The reviewed intake and its document are the record of record - an install without
    encounter support must not fail finalisation."""
    hms = _client()
    posted: list[str] = []

    def fake_request(method, url, **kwargs):
        if url.endswith("/encounter"):
            raise httpx.HTTPStatusError("nope", request=httpx.Request("POST", url), response=httpx.Response(401))
        if "/apis/default/api/" in url:
            posted.append(url.split("/apis/default/api/", 1)[1])
            if method == "GET":
                return _resp(PATIENT_ROW)
            return _resp(True if url.endswith("/document") else {"validationErrors": [], "internalErrors": [], "data": {"id": 1}})
        return _resp(PATIENT_BUNDLE)

    with patch(REST_REQUEST, side_effect=fake_request), _with_token(hms):
        hms.sync_reviewed_intake("MRN-1", {"facts": [], "entries": [], "consultation_notes": [{"notes": "n"}]})

    assert any(path.endswith("/document") for path in posted), "the summary document must still be written"


def test_sync_reviewed_intake_writes_patient_stated_rows_only():
    hms = _client()
    calls = []
    payload = {
        "facts": [{"kind": "history", "value": "asthma", "source": "patient"}, {"kind": "history", "value": "imported", "source": "hms"}],
        "entries": [{"kind": "allergy", "name": "penicillin", "reaction_or_dose": "rash", "source": "patient"},
                    {"kind": "medication", "name": "inhaler", "reaction_or_dose": None, "source": "patient"}],
    }
    with patch(REST_REQUEST, side_effect=_combined_router(calls)), _with_token(hms):
        hms.sync_reviewed_intake("MRN-1", payload)
    writes = [(path, kwargs.get("json")) for path, kwargs in _api_writes(calls)]
    assert [p for p, _ in writes] == [
        "patient/abc123/medical_problem", "patient/abc123/allergy", "patient/9/medication", "patient/9/document",
    ]
    assert writes[0][1]["title"] == "asthma"
    assert writes[1][1] == {"title": "penicillin", "begdate": writes[1][1]["begdate"], "reaction": "rash"}
    assert writes[2][1]["title"] == "inhaler" and writes[2][1]["begdate"].endswith(" 00:00:00")
    note = dict(_api_writes(calls))["patient/9/document"]["files"]["document"]
    assert note[0] == "careflow-reviewed-intake.txt" and b"kind=history, value=asthma, source=patient" in note[1]


# --- identity ----------------------------------------------------------------

def _rsa_keypair():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _jwk_dict(public_key) -> dict:
    import json

    from jwt.algorithms import RSAAlgorithm

    return json.loads(RSAAlgorithm.to_jwk(public_key))


def _signed_jwt(private_key, payload: dict, headers: dict | None = None) -> str:
    import time

    import jwt as pyjwt

    full_payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600, **payload}
    return pyjwt.encode(full_payload, private_key, algorithm="RS256", headers=headers)


def _token_response(id_token: str) -> httpx.Response:
    return _resp({"access_token": "tok", "id_token": id_token, "expires_in": 3600})


def test_verify_credentials_valid_response_returns_identity():
    hms = _client()
    private_key, public_key = _rsa_keypair()
    id_token = _signed_jwt(private_key, {"sub": "test-sub-id", "aud": "cid", "iss": "http://localhost:8300/oauth2/default"})

    with patch(TOKEN_POST, return_value=_token_response(id_token)) as mock_post:
        with patch(JWKS_GET, return_value=_resp({"keys": [_jwk_dict(public_key)]})):
            with patch.object(hms, "_request", side_effect=httpx.HTTPError("no practitioner lookup in this test")):
                identity = hms.verify_credentials("dr_mehta", "secret")

    assert identity is not None
    assert identity.id == "test-sub-id" and identity.name == "dr_mehta"
    assert mock_post.call_args.kwargs["data"]["username"] == "dr_mehta"


def test_verify_credentials_resolves_practitioner_name():
    hms = _client()
    private_key, public_key = _rsa_keypair()
    id_token = _signed_jwt(private_key, {"sub": "prac-1", "aud": "cid", "iss": "http://localhost:8300/oauth2/default"})
    with patch(TOKEN_POST, return_value=_token_response(id_token)):
        with patch(JWKS_GET, return_value=_resp({"keys": [_jwk_dict(public_key)]})):
            with patch.object(hms, "_request", return_value=_resp({"name": [{"text": "Dr. A. Mehta"}]})):
                identity = hms.verify_credentials("dr_mehta", "secret")
    assert identity is not None and identity.name == "Dr. A. Mehta"


def test_verify_credentials_missing_issuer_returns_none():
    hms = _client()
    private_key, public_key = _rsa_keypair()
    id_token = _signed_jwt(private_key, {"sub": "prac-1", "aud": "cid"})
    with patch(TOKEN_POST, return_value=_token_response(id_token)):
        with patch(JWKS_GET, return_value=_resp({"keys": [_jwk_dict(public_key)]})):
            assert hms.verify_credentials("dr_mehta", "secret") is None


def test_verify_credentials_wrong_issuer_returns_none():
    hms = _client()
    private_key, public_key = _rsa_keypair()
    id_token = _signed_jwt(private_key, {"sub": "prac-1", "aud": "cid", "iss": "https://other.example"})
    with patch(TOKEN_POST, return_value=_token_response(id_token)):
        with patch(JWKS_GET, return_value=_resp({"keys": [_jwk_dict(public_key)]})):
            assert hms.verify_credentials("dr_mehta", "secret") is None


def test_verify_credentials_tampered_signature_returns_none():
    """A token signed by a key other than the JWKS one must be rejected."""
    hms = _client()
    forger_key, _ = _rsa_keypair()
    _, real_public_key = _rsa_keypair()
    id_token = _signed_jwt(forger_key, {"sub": "attacker-controlled-id", "aud": "cid", "iss": "http://localhost:8300/oauth2/default"})

    with patch(TOKEN_POST, return_value=_token_response(id_token)):
        with patch(JWKS_GET, return_value=_resp({"keys": [_jwk_dict(real_public_key)]})):
            assert hms.verify_credentials("dr_mehta", "secret") is None


def test_verify_credentials_jwks_fetch_failure_returns_none():
    hms = _client()
    private_key, _ = _rsa_keypair()
    id_token = _signed_jwt(private_key, {"sub": "test-sub-id", "aud": "cid", "iss": "http://localhost:8300/oauth2/default"})
    with patch(TOKEN_POST, return_value=_token_response(id_token)):
        with patch(JWKS_GET, side_effect=httpx.ConnectError("down")):
            assert hms.verify_credentials("dr_mehta", "secret") is None


def test_verify_credentials_failed_token_returns_none():
    hms = _client()
    with patch(TOKEN_POST, return_value=_resp({"error": "invalid_grant"}, status_code=401)):
        assert hms.verify_credentials("dr_mehta", "wrong-password") is None


def test_verify_credentials_never_raises_on_exception():
    hms = _client()
    with patch(TOKEN_POST, side_effect=httpx.ConnectError("down")):
        assert hms.verify_credentials("dr_mehta", "secret") is None
