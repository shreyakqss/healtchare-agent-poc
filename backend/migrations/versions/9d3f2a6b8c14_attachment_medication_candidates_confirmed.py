"""medical attachments track whether their medication candidates were confirmed

Revision ID: 9d3f2a6b8c14
Revises: 7a2e9c14f6b1
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9d3f2a6b8c14'
down_revision: str | Sequence[str] | None = '7a2e9c14f6b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medical_attachments",
        sa.Column("medication_candidates_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("medical_attachments", "medication_candidates_confirmed")
