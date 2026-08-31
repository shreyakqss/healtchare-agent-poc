"""patient facts carry the clinic term their wording means

Revision ID: 3f1c7d9a4b02
Revises: ab92639e37c5
Create Date: 2026-08-31 10:12:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3f1c7d9a4b02'
down_revision: str | Sequence[str] | None = 'ab92639e37c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient_facts",
        sa.Column("normalized", sa.String(length=255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("patient_facts", "normalized")
