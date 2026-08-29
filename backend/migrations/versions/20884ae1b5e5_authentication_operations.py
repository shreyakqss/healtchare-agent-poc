"""authentication operations

Revision ID: 20884ae1b5e5
Revises: 0c667cbf8e19
Create Date: 2026-08-28 15:52:09.542038
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '20884ae1b5e5'
down_revision: str | Sequence[str] | None = '0c667cbf8e19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('rate_limit_buckets',
    sa.Column('scope', sa.String(length=64), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('request_count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scope', 'key_hash', name='uq_rate_limit_scope_key')
    )
    op.create_index(op.f('ix_rate_limit_buckets_expires_at'), 'rate_limit_buckets', ['expires_at'], unique=False)
    op.add_column('auth_sessions', sa.Column('encryption_key_id', sa.String(length=32), server_default='legacy', nullable=False))


def downgrade() -> None:
    op.drop_column('auth_sessions', 'encryption_key_id')
    op.drop_index(op.f('ix_rate_limit_buckets_expires_at'), table_name='rate_limit_buckets')
    op.drop_table('rate_limit_buckets')
