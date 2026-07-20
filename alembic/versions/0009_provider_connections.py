"""Backend-owned AI provider connections (Batch 2).

Additive: a `provider_connections` table so the backend — not the browser —
owns provider state (local Ollabridge / Ollabridge Cloud), the active provider,
and the selected model. Only safe metadata is stored; keys/tokens live in the
credential store by `secret_reference`.

Revision ID: 0009_provider_connections
Revises: 0008_identity
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_provider_connections"
down_revision = "0008_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="unconfigured"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("account_subject", sa.String(length=200), nullable=True),
        sa.Column("account_email", sa.String(length=320), nullable=True),
        sa.Column("account_display_name", sa.String(length=200), nullable=True),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("models_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("secret_reference", sa.String(length=200), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_latency_ms", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_provider_ws_kind", "provider_connections", ["workspace_id", "kind"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_provider_ws_kind", table_name="provider_connections")
    op.drop_table("provider_connections")
