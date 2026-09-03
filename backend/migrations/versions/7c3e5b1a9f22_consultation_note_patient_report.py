"""consultation notes carry the doctor's own final-draft report to the patient

Revision ID: 7c3e5b1a9f22
Revises: 5e8a1c2f7d40
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '7c3e5b1a9f22'
down_revision: str | Sequence[str] | None = '5e8a1c2f7d40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consultation_notes", sa.Column("patient_report", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("consultation_notes", "patient_report")
