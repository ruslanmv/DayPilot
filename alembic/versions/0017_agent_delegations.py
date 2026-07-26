"""Agent delegation chains (agents integration, A9).

Additive: an ``agent_delegations`` table records a manager agent delegating a
sub-task to a worker agent, so DayPilot can show the responsibility chain
(``You → manager → worker``) and audit it. The governance (no self/cycles,
depth ≤ 2, ≤ 3 workers, ≤ 10 child tasks, worker capability ≤ manager) is
enforced in code before a row is written.

Revision ID: 0017_agent_delegations
Revises: 0016_agent_account_ref
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_agent_delegations"
down_revision = "0016_agent_account_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_delegations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("manager_agent_link_id", sa.String(length=36), nullable=False),
        sa.Column("worker_agent_link_id", sa.String(length=36), nullable=False),
        sa.Column("parent_task_id", sa.String(length=36), nullable=True),
        sa.Column("child_task_id", sa.String(length=36), nullable=True),
        sa.Column("capability", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="assigned"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_delegations_ws_parent", "agent_delegations", ["workspace_id", "parent_task_id"])
    op.create_index("ix_agent_delegations_manager", "agent_delegations", ["manager_agent_link_id"])
    op.create_index("ix_agent_delegations_worker", "agent_delegations", ["worker_agent_link_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_delegations_worker", table_name="agent_delegations")
    op.drop_index("ix_agent_delegations_manager", table_name="agent_delegations")
    op.drop_index("ix_agent_delegations_ws_parent", table_name="agent_delegations")
    op.drop_table("agent_delegations")
