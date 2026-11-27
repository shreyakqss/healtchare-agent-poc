"""emergency red flags: triage rules and results carry an emergency flag; cases record when one fired

Revision ID: 8e4b1d7c3a90
Revises: 6c1f3a9e2b48
Create Date: 2026-10-21 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '8e4b1d7c3a90'
down_revision: str | Sequence[str] | None = '6c1f3a9e2b48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("triage_rules", sa.Column("emergency", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("triage_results", sa.Column("emergency", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("patient_cases", sa.Column("emergency_flagged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("patient_cases", "emergency_flagged_at")
    op.drop_column("triage_results", "emergency")
    op.drop_column("triage_rules", "emergency")
