"""push_document_with_retry: one retry, then a typed failure. No DB, no real HMS."""

from unittest.mock import MagicMock

from app.services.hms.documents import push_document_with_retry

SLEEP = "app.services.hms.documents.time.sleep"


def test_succeeds_on_first_attempt_no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(SLEEP, lambda s: slept.append(s))
    hms = MagicMock()
    hms.push_document.return_value = "DOC-1"

    assert push_document_with_retry(hms, "MRN-1", "Title", b"content") == ("DOC-1", None)
    assert hms.push_document.call_count == 1
    assert slept == []


def test_retries_once_then_succeeds(monkeypatch):
    slept = []
    monkeypatch.setattr(SLEEP, lambda s: slept.append(s))
    hms = MagicMock()
    hms.push_document.side_effect = [RuntimeError("transient"), "DOC-2"]

    assert push_document_with_retry(hms, "MRN-1", "Title", b"content") == ("DOC-2", None)
    assert hms.push_document.call_count == 2
    assert slept == [1.0]


def test_fails_after_retry_returns_none_and_error_type(monkeypatch):
    monkeypatch.setattr(SLEEP, lambda s: None)
    hms = MagicMock()
    hms.push_document.side_effect = [ConnectionError("down"), ConnectionError("still down")]

    assert push_document_with_retry(hms, "MRN-1", "Title", b"content") == (None, "ConnectionError")
    assert hms.push_document.call_count == 2
