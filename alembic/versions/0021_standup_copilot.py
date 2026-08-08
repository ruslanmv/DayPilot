"""Daily Standup Copilot: workflow, evidence and draft.

Three additive tables. ``standup_workflows`` holds the recurring configuration
and how the Slack thread is found each morning; ``standup_evidence`` holds the
traceable signals a draft is built from (never prose); ``standup_drafts`` holds
the update for one reporting day plus the frozen snapshot that approval
produces and delivery is allowed to send.

Nothing existing is modified — the standup reuses ``events``, ``audit_logs``,
``approvals`` and ``jobs`` rather than duplicating them.

Revision ID: 0021_standup_copilot
Revises: 0020_project_repository
Create Date: 2026-08-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_standup_copilot"
down_revision = "0020_project_repository"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "standup_workflows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("user_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=200), nullable=False, server_default="Daily Standup"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("working_days", sa.JSON(), nullable=False),
        sa.Column("review_time", sa.String(length=5), nullable=False, server_default="18:00"),
        sa.Column("reminder_time", sa.String(length=5), nullable=False, server_default="09:00"),
        sa.Column("delivery_mode", sa.String(length=20), nullable=False, server_default="next_workday"),
        sa.Column("slack_connection_id", sa.String(length=36), nullable=True),
        sa.Column("slack_channel_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("slack_channel_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("reminder_signature", sa.String(length=300), nullable=False,
                  server_default="Daily Standup Reminder"),
        sa.Column("reminder_bot_id", sa.String(length=64), nullable=True),
        sa.Column("thread_resolution_mode", sa.String(length=20), nullable=False, server_default="adopt"),
        sa.Column("evidence_source_config", sa.JSON(), nullable=False),
        sa.Column("approval_policy", sa.String(length=20), nullable=False, server_default="always"),
        sa.Column("empty_day_policy", sa.String(length=20), nullable=False, server_default="honest"),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_standup_workflows_workspace_id", "standup_workflows", ["workspace_id"])
    op.create_index("ix_standup_workflows_user_id", "standup_workflows", ["user_id"])
    op.create_index("ix_standup_workflows_next_review_at", "standup_workflows", ["next_review_at"])
    op.create_index("ix_standup_workflows_ws_enabled", "standup_workflows", ["workspace_id", "enabled"])

    op.create_table(
        "standup_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("reporting_date", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("activity_type", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("project_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_standup_evidence_workspace_id", "standup_evidence", ["workspace_id"])
    op.create_index("ix_standup_evidence_workflow_id", "standup_evidence", ["workflow_id"])
    op.create_index("ix_standup_evidence_reporting_date", "standup_evidence", ["reporting_date"])
    op.create_index("ix_standup_evidence_dedupe_key", "standup_evidence", ["dedupe_key"])
    op.create_index("ix_standup_evidence_day", "standup_evidence",
                    ["workflow_id", "reporting_date", "included"])

    op.create_table(
        "standup_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("reporting_date", sa.String(length=10), nullable=False),
        sa.Column("target_standup_date", sa.String(length=10), nullable=False),
        sa.Column("yesterday_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("today_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("blockers_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="COLLECTING"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("approved_yesterday", sa.Text(), nullable=True),
        sa.Column("approved_today", sa.Text(), nullable=True),
        sa.Column("approved_blockers", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("delivery_job_id", sa.String(length=36), nullable=True),
        sa.Column("delivery_key", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("slack_thread_ts", sa.String(length=40), nullable=True),
        sa.Column("slack_message_ts", sa.String(length=40), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_standup_drafts_workspace_id", "standup_drafts", ["workspace_id"])
    op.create_index("ix_standup_drafts_workflow_id", "standup_drafts", ["workflow_id"])
    op.create_index("ix_standup_drafts_reporting_date", "standup_drafts", ["reporting_date"])
    op.create_index("ix_standup_drafts_status", "standup_drafts", ["status"])
    op.create_index("ix_standup_drafts_delivery_key", "standup_drafts", ["delivery_key"])
    op.create_index("ix_standup_drafts_workflow_day", "standup_drafts",
                    ["workflow_id", "reporting_date"])


def downgrade() -> None:
    op.drop_table("standup_drafts")
    op.drop_table("standup_evidence")
    op.drop_table("standup_workflows")
