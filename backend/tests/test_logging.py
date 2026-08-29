import json
import logging
import sys

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, RequestContextFilter, bind_request_id, configure_logging, reset_request_id
from app.main import create_app


def test_structured_logs_redact_phi_and_include_request_context():
    token = bind_request_id("request-123")
    try:
        record = logging.LogRecord("careflow.test", logging.INFO, __file__, 1, "Patient %s called 5551234567", ("MRN-42",), None)
        record.http_route = "/cases/{case_id}"
        RequestContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["message"] == "Patient [MRN-REDACTED] called [PHONE-REDACTED]"
    assert payload["request_id"] == "request-123"
    assert payload["http_route"] == "/cases/{case_id}"


def test_structured_exception_records_only_the_exception_type():
    try:
        raise ValueError("Patient Alice has a sensitive condition")
    except ValueError:
        record = logging.LogRecord("careflow.test", logging.ERROR, __file__, 1, "Safe failure", (), sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert payload["exception_type"] == "ValueError"
    assert "Alice" not in json.dumps(payload)


def test_unhandled_request_error_returns_safe_response(caplog):
    test_app = create_app()

    @test_app.get("/test-unhandled")
    def fail_with_sensitive_detail():
        raise RuntimeError("Patient Alice failed")

    caplog.set_level(logging.ERROR, logger="app.main")

    response = TestClient(test_app).get("/test-unhandled?code=secret")

    assert response.status_code == 500
    assert response.json() == {"detail": "The request could not be completed."}
    assert "RuntimeError" in caplog.text
    assert "Alice" not in caplog.text
    assert "secret" not in caplog.text


def test_uvicorn_access_log_is_disabled_to_avoid_sensitive_query_logging():
    configure_logging(debug=False)

    assert logging.getLogger("uvicorn.access").disabled is True
