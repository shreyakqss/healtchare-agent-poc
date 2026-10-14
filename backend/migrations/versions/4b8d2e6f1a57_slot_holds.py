"""slot holds: one open case per practitioner time (no double booking)

Revision ID: 4b8d2e6f1a57
Revises: 2f6a8d4c1e73
Create Date: 2026-10-14 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '4b8d2e6f1a57'
down_revision: str | Sequence[str] | None = '2f6a8d4c1e73'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "slot_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("practitioner_id", sa.String(length=64), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["patient_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("practitioner_id", "slot_start", name="uq_slot_holds_practitioner_start"),
    )
    op.create_index(op.f("ix_slot_holds_practitioner_id"), "slot_holds", ["practitioner_id"])
    # Open cases routed before this table existed keep the time they already show: the
    # patient's pick, else the default. Earliest case wins if two already collide.
    op.execute("""
        INSERT INTO slot_holds (id, created_at, case_id, practitioner_id, slot_start)
        SELECT DISTINCT ON (r.doctor_id, (chosen->>'start')::timestamptz)
               gen_random_uuid(), now(), r.case_id, r.doctor_id, (chosen->>'start')::timestamptz
        FROM (
            SELECT DISTINCT ON (case_id) * FROM routing_recommendations ORDER BY case_id, created_at DESC
        ) r
        JOIN patient_cases c ON c.id = r.case_id
        JOIN intake_sessions s ON s.id = c.session_id
        CROSS JOIN LATERAL (
            SELECT COALESCE(
                (SELECT o FROM jsonb_array_elements(r.slot_options) o WHERE o->>'id' = r.selected_slot_id),
                r.suggested_slot
            ) AS chosen
        ) pick
        WHERE s.status <> 'REJECTED' AND r.doctor_id IS NOT NULL AND chosen ? 'start'
        ORDER BY r.doctor_id, (chosen->>'start')::timestamptz, r.created_at
    """)


def downgrade() -> None:
    op.drop_index(op.f("ix_slot_holds_practitioner_id"), table_name="slot_holds")
    op.drop_table("slot_holds")
