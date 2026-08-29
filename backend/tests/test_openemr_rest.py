"""OpenEMR standard-API client: request shapes and the 8.3 quirks it absorbs. httpx mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.integrations.hms.openemr.auth import OAuthConfig, TokenProvider
from app.integrations.hms.openemr.rest import StandardApi

REQUEST = "app.integrations.hms.openemr.rest.httpx.request"


def _resp(body, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=body, request=httpx.Request("GET", "http://x"))


def _api() -> StandardApi:
    return StandardApi("http://localhost:8300", "/apis/default/api", TokenProvider(OAuthConfig("http://t", "c", "s", "scope")))


def _with_token(api: StandardApi):
    return patch.object(api._tokens, "access_token", return_value="tok")


def test_patient_row_and_pid():
    api = _api()
    with patch(REQUEST, return_value=_resp({"validationErrors": [], "internalErrors": [], "data": {"id": 7, "uuid": "u", "pubpid": "7"}})) as req, _with_token(api):
        assert api.pid_for("u") == 7
    assert req.call_args.args[1].endswith("/apis/default/api/patient/u")


def test_create_medical_problem_returns_uuid_and_uses_date_only():
    api = _api()
    with patch(REQUEST, return_value=_resp({"validationErrors": [], "internalErrors": [], "data": {"id": 1, "uuid": "mp-1"}})) as req, _with_token(api):
        assert api.create_medical_problem("u", "asthma", since=date(2026, 8, 27)) == "mp-1"
    assert req.call_args.kwargs["json"] == {"title": "asthma", "begdate": "2026-08-27"}


def test_create_medication_uses_datetime_and_bare_id_reply():
    api = _api()
    with patch(REQUEST, return_value=_resp({"id": 3}, status_code=201)) as req, _with_token(api):
        assert api.create_medication(7, "inhaler", "twice daily", since=date(2026, 8, 27)) == "3"
    body = req.call_args.kwargs["json"]
    assert body["begdate"] == "2026-08-27 00:00:00" and body["comments"] == "twice daily"
    assert req.call_args.args[1].endswith("/patient/7/medication")


def test_validator_map_with_200_is_a_rejection():
    api = _api()
    with patch(REQUEST, return_value=_resp({"begdate": {"DateTime::INVALID_VALUE": "begdate must be a valid date"}})), _with_token(api):
        with pytest.raises(httpx.HTTPError):
            api.create_medication(7, "x")


def test_validation_errors_envelope_is_a_rejection():
    api = _api()
    with patch(REQUEST, return_value=_resp({"validationErrors": {"pid": ["Invalid pid"]}, "internalErrors": [], "data": None})), _with_token(api):
        with pytest.raises(httpx.HTTPError):
            api.create_allergy("u", "penicillin")


def test_upload_document_is_multipart_into_documents_category():
    api = _api()
    with patch(REQUEST, return_value=_resp(True)) as req, _with_token(api):
        assert api.upload_document(7, "visit-summary.txt", b"hi", "text/plain") is True
    assert req.call_args.args[1].endswith("/patient/7/document")
    assert req.call_args.kwargs["params"] == {"path": "/Documents"}
    assert req.call_args.kwargs["files"]["document"] == ("visit-summary.txt", b"hi", "text/plain")


def test_create_encounter_is_keyed_on_the_patient_uuid_and_returns_the_encounter_number():
    """Encounters address the patient by uuid (this endpoint resolves it), and OpenEMR
    answers with `eid`/`euuid` rather than `id`/`uuid`. The numeric `eid` is what comes
    back, because a form can only be filed against the numeric encounter number."""
    api = _api()
    reply = {"validationErrors": [], "internalErrors": [], "data": {"eid": 12, "euuid": "enc-uuid"}}
    with patch(REQUEST, return_value=_resp(reply)) as req, _with_token(api):
        assert api.create_encounter("pat-uuid", "Headache", when=date(2026, 8, 27)) == 12
    assert req.call_args.args[1].endswith("/patient/pat-uuid/encounter")
    assert req.call_args.kwargs["json"] == {
        "pc_catid": "5", "class_code": "AMB", "reason": "Headache", "date": "2026-08-27",
    }


def test_soap_note_is_filed_against_numeric_ids_and_never_invents_a_section():
    """Two rules in one call. The path must carry numeric pid/encounter: OpenEMR writes them
    into `form_soap.pid` and `forms.encounter` unvalidated, so a uuid is cast to 0 and the
    note is accepted but orphaned. And a section CareFlow never collected must not be filled
    with invented clinical content - OpenEMR rejects anything under two characters."""
    api = _api()
    with patch(REQUEST, return_value=_resp({"validationErrors": [], "internalErrors": [], "data": {}})) as req, _with_token(api):
        api.create_soap_note(9, 12, subjective="Headache", objective="",
                             assessment="Tension-type pattern.", plan="")
    body = req.call_args.kwargs["json"]
    assert req.call_args.args[1].endswith("/patient/9/encounter/12/soap_note")
    assert body["subjective"] == "Headache" and body["assessment"] == "Tension-type pattern."
    assert body["objective"] == body["plan"] == "Not recorded during intake."
    assert all(len(section) >= 2 for section in body.values())


def test_lists_treat_404_and_500_as_empty():
    api = _api()
    for status in (404, 500):
        with patch(REQUEST, return_value=_resp({"error": "x"}, status_code=status)), _with_token(api):
            assert api.medications(7) == []
