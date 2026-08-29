"""Unit tests for attachment storage guards and the advisory kind heuristic."""

import pytest

from app.core.config import settings
from app.services.attachments import absolute_path, kind_mismatch_suspected


def test_storage_path_cannot_escape_upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        absolute_path("../outside.txt")


def test_storage_path_resolves_inside_upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    assert absolute_path("case/file.txt") == (tmp_path / "case/file.txt").resolve()


def test_no_text_is_never_flagged():
    assert kind_mismatch_suspected("lab_report", None) is False
    assert kind_mismatch_suspected("lab_report", "") is False


def test_kind_with_no_keyword_set_is_never_flagged():
    assert kind_mismatch_suspected("other", "literally anything at all") is False


def test_matching_lab_report_text_not_flagged():
    text = "CBC panel result: Hemoglobin 13.2 g/dl, within reference range, normal."
    assert kind_mismatch_suspected("lab_report", text) is False


def test_mismatched_lab_report_text_flagged():
    text = "Please refer patient to a specialist for further consultation."
    assert kind_mismatch_suspected("lab_report", text) is True


def test_matching_prescription_text_not_flagged():
    text = "Rx: Amoxicillin 500mg tablet, twice daily for 7 days."
    assert kind_mismatch_suspected("prescription", text) is False


def test_mismatched_prescription_text_flagged():
    text = "MRI findings show no acute abnormality on imaging."
    assert kind_mismatch_suspected("prescription", text) is True


def test_case_insensitive_matching():
    text = "IMPRESSION: Chest X-RAY shows clear lung fields."
    assert kind_mismatch_suspected("radiology", text) is False
