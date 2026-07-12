"""Integration platform foundation — connection records (batch I0).

Additive only: a new `integration_connections` table. Credentials are never
stored here; they live in the secrets backend keyed by connection id.

Revision ID: 0005_integration_connections
Revises: 0004_jobs_queue
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_integration_connections"
down_revision = "0004_jobs_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("provider", sa.String(length=80), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("auth_type", sa.String(length=20), nullable=False, server_default="api_key"),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("permissions_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_integration_connections_ws_provider",
        "integration_connections",
        ["workspace_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_connections_ws_provider", table_name="integration_connections")
    op.drop_table("integration_connections")
