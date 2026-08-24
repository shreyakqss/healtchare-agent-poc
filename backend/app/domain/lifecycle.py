"""Case lifecycle guard.

CREATED -> INGESTING -> ANALYZING -> NEEDS_REVIEW -> APPROVED -> COMPLETED,
with REJECTED and FAILED as terminal branches.
"""

from __future__ import annotations

from enum import StrEnum


class CaseStatus(StrEnum):
    CREATED = "CREATED"
    INGESTING = "INGESTING"
    ANALYZING = "ANALYZING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


ALLOWED: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.CREATED: {CaseStatus.INGESTING, CaseStatus.REJECTED, CaseStatus.FAILED},
    CaseStatus.INGESTING: {CaseStatus.INGESTING, CaseStatus.ANALYZING, CaseStatus.REJECTED, CaseStatus.FAILED},
    CaseStatus.ANALYZING: {CaseStatus.NEEDS_REVIEW, CaseStatus.INGESTING, CaseStatus.FAILED},
    CaseStatus.NEEDS_REVIEW: {CaseStatus.APPROVED, CaseStatus.REJECTED, CaseStatus.ANALYZING, CaseStatus.FAILED},
    CaseStatus.APPROVED: {CaseStatus.COMPLETED, CaseStatus.NEEDS_REVIEW, CaseStatus.FAILED},
    CaseStatus.COMPLETED: set(),
    CaseStatus.REJECTED: set(),
    CaseStatus.FAILED: {CaseStatus.INGESTING, CaseStatus.ANALYZING},
}

TERMINAL = {CaseStatus.COMPLETED, CaseStatus.REJECTED}


class IllegalTransition(RuntimeError):
    pass


def assert_transition(current: str, target: str) -> None:
    if current == target:
        return
    try:
        allowed = ALLOWED[CaseStatus(current)]
    except ValueError as exc:
        raise IllegalTransition(f"Unknown status {current!r}.") from exc
    if CaseStatus(target) not in allowed:
        raise IllegalTransition(
            f"Cannot move a case from {current} to {target}. "
            f"Allowed: {', '.join(sorted(allowed)) or '(terminal)'}."
        )