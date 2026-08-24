import pytest

from app.domain.lifecycle import CaseStatus, IllegalTransition, assert_transition


def test_happy_path():
    path = ["CREATED", "INGESTING", "ANALYZING", "NEEDS_REVIEW", "APPROVED", "COMPLETED"]
    for a, b in zip(path, path[1:], strict=False):
        assert_transition(a, b)


def test_cannot_skip_review():
    with pytest.raises(IllegalTransition):
        assert_transition(CaseStatus.ANALYZING, CaseStatus.COMPLETED)


def test_terminal_is_terminal():
    with pytest.raises(IllegalTransition):
        assert_transition(CaseStatus.COMPLETED, CaseStatus.INGESTING)