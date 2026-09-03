"""routing recommendations carry multiple slot options + the patient's pick

Revision ID: 5e8a1c2f7d40
Revises: 1b7f4e2a9c33
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5e8a1c2f7d40'
down_revision: str | Sequence[str] | None = '1b7f4e2a9c33'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "routing_recommendations",
        sa.Column("slot_options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "routing_recommendations",
        sa.Column("selected_slot_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("routing_recommendations", "selected_slot_id")
    op.drop_column("routing_recommendations", "slot_options")
