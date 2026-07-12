"""Persistent assistant chat sessions and messages.

Additive: two new tables backing ChatGPT/Claude-style conversation history —
`chat_sessions` (one per conversation) and `chat_messages` (one per turn).
Only conversation text is stored; credentials/keys are never persisted.

Revision ID: 0007_chat_sessions
Revises: 0006_mcp_connections
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_chat_sessions"
down_revision = "0006_mcp_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("title", sa.String(length=200), nullable=False, server_default="New conversation"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_ws_updated", "chat_sessions", ["workspace_id", "updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_session_seq", "chat_messages", ["session_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_seq", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_ws_updated", table_name="chat_sessions")
    op.drop_table("chat_sessions")
