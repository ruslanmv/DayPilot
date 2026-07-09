"""Initial DayPilot core schema.

Revision ID: 0001_initial_core_schema
Revises:
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True, index=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "personas",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="daypilot"),
        sa.Column("install_state", sa.String(length=80), nullable=False, server_default="INSTALLED_DISABLED"),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("write_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("policy_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "calendar_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_account_id", sa.String(length=320), nullable=False),
        sa.Column("sync_state", sa.String(length=80), nullable=False, server_default="disabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "inbox_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("external_account_id", sa.String(length=320), nullable=False),
        sa.Column("sync_state", sa.String(length=80), nullable=False, server_default="disabled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("source_uri", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True, index=True),
        sa.Column("ingest_state", sa.String(length=80), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_ref", sa.String(length=500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("persona_id", sa.String(length=80), sa.ForeignKey("personas.id"), nullable=True, index=True),
        sa.Column("event_type", sa.String(length=120), nullable=False, index=True),
        sa.Column("risk", sa.String(length=40), nullable=False, server_default="low"),
        sa.Column("decision", sa.String(length=80), nullable=False, server_default="recorded"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("inbox_accounts")
    op.drop_table("calendar_accounts")
    op.drop_table("personas")
    op.drop_table("users")
