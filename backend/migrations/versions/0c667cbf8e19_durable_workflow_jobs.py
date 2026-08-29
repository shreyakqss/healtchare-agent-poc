"""durable workflow jobs

Revision ID: 0c667cbf8e19
Revises: 20260828_0001
Create Date: 2026-08-28 12:06:37.807542
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0c667cbf8e19'
down_revision: str | Sequence[str] | None = '20260828_0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('workflow_jobs',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('workflow', sa.String(length=32), nullable=False),
    sa.Column('operation_key', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_by', sa.String(length=128), nullable=True),
    sa.Column('last_error_code', sa.String(length=128), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operation_key', name='uq_workflow_job_operation')
    )
    op.create_index(op.f('ix_workflow_jobs_available_at'), 'workflow_jobs', ['available_at'], unique=False)
    op.create_index(op.f('ix_workflow_jobs_case_id'), 'workflow_jobs', ['case_id'], unique=False)
    op.create_index(op.f('ix_workflow_jobs_lease_expires_at'), 'workflow_jobs', ['lease_expires_at'], unique=False)
    op.create_index(op.f('ix_workflow_jobs_status'), 'workflow_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_workflow_jobs_workflow'), 'workflow_jobs', ['workflow'], unique=False)
    op.create_table('workflow_operations',
    sa.Column('case_id', sa.Uuid(), nullable=False),
    sa.Column('operation_key', sa.String(length=180), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('last_error_code', sa.String(length=128), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['case_id'], ['patient_cases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('operation_key', name='uq_workflow_operation_key')
    )
    op.create_index(op.f('ix_workflow_operations_case_id'), 'workflow_operations', ['case_id'], unique=False)
    op.create_index(op.f('ix_workflow_operations_kind'), 'workflow_operations', ['kind'], unique=False)
    op.create_index(op.f('ix_workflow_operations_status'), 'workflow_operations', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workflow_operations_status'), table_name='workflow_operations')
    op.drop_index(op.f('ix_workflow_operations_kind'), table_name='workflow_operations')
    op.drop_index(op.f('ix_workflow_operations_case_id'), table_name='workflow_operations')
    op.drop_table('workflow_operations')
    op.drop_index(op.f('ix_workflow_jobs_workflow'), table_name='workflow_jobs')
    op.drop_index(op.f('ix_workflow_jobs_status'), table_name='workflow_jobs')
    op.drop_index(op.f('ix_workflow_jobs_lease_expires_at'), table_name='workflow_jobs')
    op.drop_index(op.f('ix_workflow_jobs_case_id'), table_name='workflow_jobs')
    op.drop_index(op.f('ix_workflow_jobs_available_at'), table_name='workflow_jobs')
    op.drop_table('workflow_jobs')
