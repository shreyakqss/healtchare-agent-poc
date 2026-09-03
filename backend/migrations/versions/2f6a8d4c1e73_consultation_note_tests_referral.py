"""consultation notes carry tests ordered and notes for other doctors

Revision ID: 2f6a8d4c1e73
Revises: 7c3e5b1a9f22
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '2f6a8d4c1e73'
down_revision: str | Sequence[str] | None = '7c3e5b1a9f22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consultation_notes", sa.Column("tests_ordered", sa.Text(), nullable=True))
    op.add_column("consultation_notes", sa.Column("referral_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("consultation_notes", "referral_notes")
    op.drop_column("consultation_notes", "tests_ordered")
