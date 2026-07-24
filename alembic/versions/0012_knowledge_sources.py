"""Persistent knowledge sources (Issue 1).

Additive: a `knowledge_sources` table so the backend owns granted RAG sources —
the Settings screen lists real rows and re-indexing runs as a durable job,
instead of hard-coded sample data with dead buttons.

Revision ID: 0012_knowledge_sources
Revises: 0011_assistant_runs
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012_knowledge_sources"
down_revision = "0011_assistant_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("display_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("location", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("scope", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("permission", sa.String(length=20), nullable=False, server_default="read_index"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("project_ids", sa.JSON(), nullable=True),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_sources_ws", "knowledge_sources", ["workspace_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_sources_ws", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
