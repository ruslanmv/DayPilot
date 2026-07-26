"""Agent-workspace fields on chat_sessions (agents integration, PR 06 / A4).

Additive: a chat session is either the shared assistant (``kind='assistant'``,
the default for every existing row) or one agent's dedicated workspace
(``kind='agent'``). For an agent session ``agent_link_id`` references the
HomePilotAgentLink, and the remote ids let a later batch resume HomePilot's own
conversation. HomePilot owns the remote conversation; DayPilot stores only the
reference — never the persona prompt or memory (contract rule 5).

Revision ID: 0014_chat_session_agent_kind
Revises: 0013_homepilot_agent_links
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_chat_session_agent_kind"
down_revision = "0013_homepilot_agent_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="assistant"),
    )
    op.add_column("chat_sessions", sa.Column("agent_link_id", sa.String(length=36), nullable=True))
    op.add_column("chat_sessions", sa.Column("remote_session_id", sa.String(length=120), nullable=True))
    op.add_column("chat_sessions", sa.Column("remote_conversation_id", sa.String(length=120), nullable=True))
    op.create_index("ix_chat_sessions_agent_link", "chat_sessions", ["agent_link_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_agent_link", table_name="chat_sessions")
    op.drop_column("chat_sessions", "remote_conversation_id")
    op.drop_column("chat_sessions", "remote_session_id")
    op.drop_column("chat_sessions", "agent_link_id")
    op.drop_column("chat_sessions", "kind")
