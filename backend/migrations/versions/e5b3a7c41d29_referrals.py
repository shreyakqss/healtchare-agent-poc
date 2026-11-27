"""referrals: a doctor sends a patient on to another department, opening a linked visit

Revision ID: e5b3a7c41d29
Revises: d2a6c9e51f08
Create Date: 2026-11-27 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5b3a7c41d29'
down_revision: str | Sequence[str] | None = 'd2a6c9e51f08'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_case_id", sa.Uuid(), sa.ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_doctor_id", sa.String(64), nullable=False),
        sa.Column("from_doctor_name", sa.String(128), nullable=False),
        sa.Column("from_department_name", sa.String(128), nullable=True),
        sa.Column("to_department_id", sa.String(64), nullable=False),
        sa.Column("to_department_name", sa.String(128), nullable=False),
        sa.Column("to_doctor_id", sa.String(64), nullable=True),
        sa.Column("to_doctor_name", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(16), nullable=False, server_default="routine"),
        sa.Column("hms_reference", sa.String(128), nullable=True),
    )
    op.create_index("ix_referrals_source_case_id", "referrals", ["source_case_id"])
    op.create_index("ix_referrals_case_id", "referrals", ["case_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_referrals_case_id", table_name="referrals")
    op.drop_index("ix_referrals_source_case_id", table_name="referrals")
    op.drop_table("referrals")
