"""doctor assistant messages: the clinician's AI assistant chat is kept per case

Revision ID: b4d7e2a91c06
Revises: 9a1c5e3f7b20
Create Date: 2026-11-02 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b4d7e2a91c06'
down_revision: str | Sequence[str] | None = '9a1c5e3f7b20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "doctor_assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("patient_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("author_id", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doctor_assistant_messages_case_id", "doctor_assistant_messages", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_doctor_assistant_messages_case_id", table_name="doctor_assistant_messages")
    op.drop_table("doctor_assistant_messages")
