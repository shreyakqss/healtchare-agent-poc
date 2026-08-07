"""Guard for the documented run-state lifecycle.

CREATED -> INGESTING -> ANALYZING -> NEEDS_REVIEW -> APPROVED -> COMPLETED,
with REJECTED and FAILED as terminal branches.

Every status write goes through `apply_transition`, so an illegal jump (a case
reaching COMPLETED without a clinician approving it, say) fails loudly instead
of quietly corrupting the demo.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import AuditEvent, IntakeSession

ALLOWED: dict[str, set[str]] = {
    "CREATED": {"INGESTING", "REJECTED", "FAILED"},
    "INGESTING": {"INGESTING", "ANALYZING", "REJECTED", "FAILED"},
    "ANALYZING": {"NEEDS_REVIEW", "INGESTING", "FAILED"},
    "NEEDS_REVIEW": {"APPROVED", "REJECTED", "ANALYZING", "FAILED"},
    "APPROVED": {"COMPLETED", "NEEDS_REVIEW", "FAILED"},
    "COMPLETED": set(),
    "REJECTED": set(),
    "FAILED": {"INGESTING", "ANALYZING"},
}

TERMINAL = {"COMPLETED", "REJECTED"}


class IllegalTransition(RuntimeError):
    pass


def assert_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = ALLOWED.get(current)
    if allowed is None:
        raise IllegalTransition(f"Unknown current status '{current}'.")
    if target not in allowed:
        raise IllegalTransition(
            f"Cannot move a case from {current} to {target}. "
            f"Allowed from {current}: {', '.join(sorted(allowed)) or '(terminal)'}."
        )


def apply_transition(
    db: Session, session: IntakeSession, target: str, actor: str, case_id=None
) -> IntakeSession:
    """Validate, write, and audit a status change."""
    assert_transition(session.status, target)
    previous = session.status
    session.status = target

    if case_id is not None and previous != target:
        db.add(
            AuditEvent(
                case_id=case_id,
                actor=actor,
                action="status.changed",
                payload={"from": previous, "to": target},
            )
        )
    db.commit()
    db.refresh(session)
    return session
