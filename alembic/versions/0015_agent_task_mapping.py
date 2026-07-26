"""Agent task-mapping fields on tasks + agent_runs (agents integration, A7).

Additive: a task produced from a HomePilot persona directive records which agent
owns/manages/created it, its progress, an optional parent (delegation, Phase 10),
the safe proposal payload for an external-write proposal, and the Approval that
gates it. agent_runs gains the owning agent link. Existing rows default cleanly
(progress 0, no agent, empty reference).

Revision ID: 0015_agent_task_mapping
Revises: 0014_chat_session_agent_kind
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_agent_task_mapping"
down_revision = "0014_chat_session_agent_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("assigned_agent_link_id", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("manager_agent_link_id", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("created_by_agent_link_id", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("parent_task_id", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tasks", sa.Column("remote_reference", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("tasks", sa.Column("approval_id", sa.String(length=36), nullable=True))
    op.create_index("ix_tasks_assigned_agent", "tasks", ["assigned_agent_link_id"])
    op.create_index("ix_tasks_parent", "tasks", ["parent_task_id"])

    op.add_column("agent_runs", sa.Column("agent_link_id", sa.String(length=36), nullable=True))
    op.create_index("ix_agent_runs_agent_link", "agent_runs", ["agent_link_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_agent_link", table_name="agent_runs")
    op.drop_column("agent_runs", "agent_link_id")

    op.drop_index("ix_tasks_parent", table_name="tasks")
    op.drop_index("ix_tasks_assigned_agent", table_name="tasks")
    op.drop_column("tasks", "approval_id")
    op.drop_column("tasks", "remote_reference")
    op.drop_column("tasks", "progress_percent")
    op.drop_column("tasks", "parent_task_id")
    op.drop_column("tasks", "created_by_agent_link_id")
    op.drop_column("tasks", "manager_agent_link_id")
    op.drop_column("tasks", "assigned_agent_link_id")
