"""MCP server connections (batch I4/I5).

Additive: a new `mcp_connections` table for attached remote/local MCP servers.

Revision ID: 0006_mcp_connections
Revises: 0005_integration_connections
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_mcp_connections"
down_revision = "0005_integration_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("transport", sa.String(length=20), nullable=False, server_default="streamable_http"),
        sa.Column("endpoint", sa.String(length=500), nullable=True),
        sa.Column("command", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="connected"),
        sa.Column("enabled_tools", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tools_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("overrides_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mcp_connections_ws", "mcp_connections", ["workspace_id", "name"])


def downgrade() -> None:
    op.drop_index("ix_mcp_connections_ws", table_name="mcp_connections")
    op.drop_table("mcp_connections")
