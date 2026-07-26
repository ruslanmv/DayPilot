"""HomePilot remote agent links (agents integration, PR 03).

Additive: a `homepilot_agent_links` table holding DayPilot-side *references* to
HomePilot personas — safe display metadata + local ownership flags only. The
persona prompt/memory are never stored (contract rule 5). Unique per
(workspace, connection, homepilot_project_id).

Revision ID: 0013_homepilot_agent_links
Revises: 0012_knowledge_sources
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013_homepilot_agent_links"
down_revision = "0012_knowledge_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepilot_agent_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("connection_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("homepilot_project_id", sa.String(length=120), nullable=False),
        sa.Column("homepilot_model_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("avatar_ref", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_ref", sa.String(length=500), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("memory_mode", sa.String(length=40), nullable=True),
        sa.Column("source_version", sa.String(length=120), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="disabled"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_homepilot_link_unique",
        "homepilot_agent_links",
        ["workspace_id", "connection_id", "homepilot_project_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_homepilot_link_unique", table_name="homepilot_agent_links")
    op.drop_table("homepilot_agent_links")
