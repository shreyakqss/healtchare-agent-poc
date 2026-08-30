"""patient account linking: user email/display_name/hms_patient_id, drop demographics cache

Revision ID: ab92639e37c5
Revises: 20884ae1b5e5
Create Date: 2026-08-29 18:29:39.038963
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'ab92639e37c5'
down_revision: str | Sequence[str] | None = '20884ae1b5e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("application_users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("application_users", sa.Column("hms_patient_id", sa.String(length=64), nullable=True))
    op.drop_column("patient_cases", "demographics")


def downgrade() -> None:
    op.add_column("patient_cases", sa.Column("demographics", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.drop_column("application_users", "hms_patient_id")
    op.drop_column("application_users", "display_name")
    op.drop_column("application_users", "email")
