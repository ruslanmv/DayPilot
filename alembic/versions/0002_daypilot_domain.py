"""DayPilot domain schema (batch B1).

Adds the persistent domain model for tasks, projects, agent runs, day plans,
plan blocks, approvals, the Today Context event stream, coding runs, email
items, and calendar events. Extends documents with project/status/source and
the composite index required for scale.

Revision ID: 0002_daypilot_domain
Revises: 0001_initial_core_schema
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_daypilot_domain"
down_revision = "0001_initial_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="Active"),
        sa.Column("risk", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("ai_activity", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_human_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("continue_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("ai_actions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("designer_input", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recent_signals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("linked_sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("yesterday", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("today", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("blocked", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_projects_ws_status_risk", "projects", ["workspace_id", "status", "risk"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("owner", sa.String(length=20), nullable=False, server_default="you"),
        sa.Column("executor", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("day", sa.String(length=20), nullable=True),
        sa.Column("start_time", sa.String(length=8), nullable=True),
        sa.Column("end_time", sa.String(length=8), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_impact", sa.Text(), nullable=True),
        sa.Column("parallel_ai", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_tasks_owner_status_project_due",
        "tasks",
        ["workspace_id", "owner", "status", "project_id", "due_date"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("agent_kind", sa.String(length=80), nullable=False, server_default="assistant"),
        sa.Column("current_work", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("display_status", sa.String(length=40), nullable=False, server_default="Running"),
        sa.Column("provider", sa.String(length=80), nullable=False, server_default="Ollabridge"),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="Local"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_state_updated", "agent_runs", ["state", "updated_at"])

    op.create_table(
        "day_plans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("plan_date", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_day_plans_ws_date", "day_plans", ["workspace_id", "plan_date"])

    op.create_table(
        "plan_blocks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("day_plan_id", sa.String(length=36), sa.ForeignKey("day_plans.id"), nullable=False, index=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start_time", sa.String(length=8), nullable=True),
        sa.Column("end_time", sa.String(length=8), nullable=True),
        sa.Column("owner", sa.String(length=20), nullable=False, server_default="you"),
        sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="scheduled"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("persona_id", sa.String(length=80), sa.ForeignKey("personas.id"), nullable=True),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approvals_ws_status_created", "approvals", ["workspace_id", "status", "created_at"])

    op.create_table(
        "events",
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("type", sa.String(length=80), nullable=False, index=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_events_ws_seq", "events", ["workspace_id", "seq"])

    op.create_table(
        "coding_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("executor", sa.String(length=40), nullable=False, server_default="gitpilot"),
        sa.Column("repo", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("branch", sa.String(length=200), nullable=True),
        sa.Column("pr_url", sa.String(length=500), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="ask"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("files_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tests_passed", sa.Integer(), nullable=True),
        sa.Column("tests_total", sa.Integer(), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_coding_runs_ws_status_updated", "coding_runs", ["workspace_id", "status", "updated_at"])

    op.create_table(
        "email_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("inbox_account_id", sa.String(length=36), sa.ForeignKey("inbox_accounts.id"), nullable=True),
        sa.Column("external_id", sa.String(length=320), nullable=True, index=True),
        sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("sender", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("urgency", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("intent", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("classification_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="new"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_items_ws_status_received", "email_items", ["workspace_id", "status", "received_at"])

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("calendar_account_id", sa.String(length=36), sa.ForeignKey("calendar_accounts.id"), nullable=True),
        sa.Column("external_id", sa.String(length=320), nullable=True, index=True),
        sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(length=80), nullable=False, server_default="you"),
        sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="confirmed"),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_calendar_events_ws_start", "calendar_events", ["workspace_id", "start_at"])

    # Extend documents with project linkage and routing metadata. The column is
    # added without a DB-level FK constraint because SQLite cannot ALTER a table
    # to add a constraint; the ORM relationship still resolves the link.
    op.add_column("documents", sa.Column("project_id", sa.String(length=36), nullable=True))
    op.add_column("documents", sa.Column("status", sa.String(length=80), nullable=False, server_default="Not Yet Indexed"))
    op.add_column("documents", sa.Column("source", sa.String(length=80), nullable=False, server_default="Local PC"))
    op.create_index("ix_documents_project_id", "documents", ["project_id"])
    op.create_index("ix_documents_project_status_source", "documents", ["project_id", "status", "source"])


def downgrade() -> None:
    op.drop_index("ix_documents_project_status_source", table_name="documents")
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_column("documents", "source")
    op.drop_column("documents", "status")
    op.drop_column("documents", "project_id")
    op.drop_index("ix_calendar_events_ws_start", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_index("ix_email_items_ws_status_received", table_name="email_items")
    op.drop_table("email_items")
    op.drop_index("ix_coding_runs_ws_status_updated", table_name="coding_runs")
    op.drop_table("coding_runs")
    op.drop_index("ix_events_ws_seq", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_approvals_ws_status_created", table_name="approvals")
    op.drop_table("approvals")
    op.drop_table("plan_blocks")
    op.drop_index("ix_day_plans_ws_date", table_name="day_plans")
    op.drop_table("day_plans")
    op.drop_index("ix_agent_runs_state_updated", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_tasks_owner_status_project_due", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_projects_ws_status_risk", table_name="projects")
    op.drop_table("projects")
