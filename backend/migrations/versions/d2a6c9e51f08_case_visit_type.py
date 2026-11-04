"""case visit type: a follow-up visit links to the completed visit it follows up

Revision ID: d2a6c9e51f08
Revises: c8e1f4b27d93
Create Date: 2026-11-03 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd2a6c9e51f08'
down_revision: str | Sequence[str] | None = 'c8e1f4b27d93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("patient_cases", sa.Column("visit_type", sa.String(16), nullable=False, server_default="new"))
    op.add_column("patient_cases", sa.Column("follow_up_of", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_patient_cases_follow_up_of", "patient_cases", "patient_cases", ["follow_up_of"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_patient_cases_follow_up_of", "patient_cases", ["follow_up_of"])


def downgrade() -> None:
    op.drop_index("ix_patient_cases_follow_up_of", table_name="patient_cases")
    op.drop_constraint("fk_patient_cases_follow_up_of", "patient_cases", type_="foreignkey")
    op.drop_column("patient_cases", "follow_up_of")
    op.drop_column("patient_cases", "visit_type")
