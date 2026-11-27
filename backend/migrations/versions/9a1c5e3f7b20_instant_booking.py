"""instant booking: a case records the appointment it booked on the doctor's HMS calendar

Revision ID: 9a1c5e3f7b20
Revises: 8e4b1d7c3a90
Create Date: 2026-10-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '9a1c5e3f7b20'
down_revision: str | Sequence[str] | None = '8e4b1d7c3a90'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient_cases", sa.Column("hms_appointment_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("patient_cases", "hms_appointment_id")
