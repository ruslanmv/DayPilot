"""Slack Workspace: preferences, traced conversations/messages, drafts.

Five additive tables. ``slack_preferences`` holds what may be drafted and — the
part that matters — the allow-list of context a draft may read plus the
recipient-protection policy. ``slack_conversations`` / ``slack_messages`` are the
traced record for conversations the user opted in to. ``slack_drafts`` and
``slack_draft_revisions`` hold prepared messages and their edit history, so
"Use this" can be undone across a reload.

Nothing existing is modified. Slack connections stay in
``integration_connections`` and sending keeps going through ``approvals`` — there
is deliberately no column anywhere that could enable automatic sending.

Revision ID: 0023_slack_workspace
Revises: 0022_calendar_settings
Create Date: 2026-08-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_slack_workspace"
down_revision = "0022_calendar_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_preferences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("draft_direct_messages", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("draft_mentions", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("draft_participating_threads", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("draft_all_channel_messages", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("auto_prepare", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("context_sources", sa.JSON(), nullable=False),
        sa.Column("use_previous_conversations", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("recipient_protection", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("access_mode", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_slack_preferences_workspace_id", "slack_preferences",
                    ["workspace_id"], unique=True)

    op.create_table(
        "slack_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("channel_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="channel"),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("counterpart", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("audience", sa.String(length=20), nullable=False, server_default="internal"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_slack_conversations_ws_channel", "slack_conversations",
                    ["workspace_id", "channel_id"], unique=True)
    op.create_index("ix_slack_conversations_connection_id", "slack_conversations",
                    ["connection_id"])

    op.create_table(
        "slack_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("conversation_id", sa.String(length=36),
                  sa.ForeignKey("slack_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.String(length=40), nullable=False),
        sa.Column("thread_ts", sa.String(length=40), nullable=True),
        sa.Column("author_id", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("direction", sa.String(length=10), nullable=False, server_default="incoming"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("classification", sa.String(length=30), nullable=False, server_default="fyi"),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("handled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_slack_messages_conv_ts", "slack_messages",
                    ["conversation_id", "ts"], unique=True)
    op.create_index("ix_slack_messages_classification", "slack_messages", ["classification"])

    op.create_table(
        "slack_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("conversation_id", sa.String(length=36),
                  sa.ForeignKey("slack_conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="reply"),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("classification", sa.String(length=30), nullable=False,
                  server_default="needs_reply"),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("withheld_json", sa.JSON(), nullable=False),
        sa.Column("backend", sa.String(length=40), nullable=False, server_default="deterministic"),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("sent_ts", sa.String(length=40), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_slack_drafts_ws_status", "slack_drafts", ["workspace_id", "status"])

    op.create_table(
        "slack_draft_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("draft_id", sa.String(length=36),
                  sa.ForeignKey("slack_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_slack_draft_revisions_draft_id", "slack_draft_revisions", ["draft_id"])


def downgrade() -> None:
    op.drop_index("ix_slack_draft_revisions_draft_id", table_name="slack_draft_revisions")
    op.drop_table("slack_draft_revisions")
    op.drop_index("ix_slack_drafts_ws_status", table_name="slack_drafts")
    op.drop_table("slack_drafts")
    op.drop_index("ix_slack_messages_classification", table_name="slack_messages")
    op.drop_index("ix_slack_messages_conv_ts", table_name="slack_messages")
    op.drop_table("slack_messages")
    op.drop_index("ix_slack_conversations_connection_id", table_name="slack_conversations")
    op.drop_index("ix_slack_conversations_ws_channel", table_name="slack_conversations")
    op.drop_table("slack_conversations")
    op.drop_index("ix_slack_preferences_workspace_id", table_name="slack_preferences")
    op.drop_table("slack_preferences")
