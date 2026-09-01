"""medical attachments carry extracted medication candidates

Revision ID: 7a2e9c14f6b1
Revises: 3f1c7d9a4b02
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '7a2e9c14f6b1'
down_revision: str | Sequence[str] | None = '3f1c7d9a4b02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medical_attachments",
        sa.Column("extracted_medications", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("medical_attachments", "extracted_medications")
