"""admin audit events: clinic-level admin actions (adding a doctor)

Revision ID: 6c1f3a9e2b48
Revises: 4b8d2e6f1a57
Create Date: 2026-10-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6c1f3a9e2b48'
down_revision: str | Sequence[str] | None = '4b8d2e6f1a57'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinic_id", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_audit_events_clinic_id"), "admin_audit_events", ["clinic_id"])
    op.create_index(op.f("ix_admin_audit_events_action"), "admin_audit_events", ["action"])


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_events_action"), table_name="admin_audit_events")
    op.drop_index(op.f("ix_admin_audit_events_clinic_id"), table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
