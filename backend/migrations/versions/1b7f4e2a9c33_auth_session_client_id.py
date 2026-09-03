"""auth sessions track which OIDC client minted their tokens, so refresh uses the right client

Revision ID: 1b7f4e2a9c33
Revises: 9d3f2a6b8c14
Create Date: 2026-09-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '1b7f4e2a9c33'
down_revision: str | Sequence[str] | None = '9d3f2a6b8c14'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("client_id", sa.String(length=255), nullable=False, server_default="careflow-web"),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "client_id")
