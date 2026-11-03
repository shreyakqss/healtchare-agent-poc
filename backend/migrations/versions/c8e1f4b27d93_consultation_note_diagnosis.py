"""consultation note diagnosis: the report's provisional diagnosis is its own section

Revision ID: c8e1f4b27d93
Revises: b4d7e2a91c06
Create Date: 2026-11-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c8e1f4b27d93'
down_revision: str | Sequence[str] | None = 'b4d7e2a91c06'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("consultation_notes", sa.Column("diagnosis", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("consultation_notes", "diagnosis")
