"""Assistant orchestrator runs (Batch 4).

Additive: `assistant_runs` and `assistant_run_events` so the backend owns
assistant intent routing and capability dispatch, with a durable audit trail of
the classified intent, tools invoked (and their risk class), and the
deterministic reply/action for each turn.

Revision ID: 0011_assistant_runs
Revises: 0010_mailbox_connections
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011_assistant_runs"
down_revision = "0010_mailbox_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("session_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("intent", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_json", sa.JSON(), nullable=True),
        sa.Column("tools_json", sa.JSON(), nullable=True),
        sa.Column("limited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="deterministic"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_runs_ws_created", "assistant_runs", ["workspace_id", "created_at"])

    op.create_table(
        "assistant_run_events",
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_run_events_run_seq", "assistant_run_events", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_assistant_run_events_run_seq", table_name="assistant_run_events")
    op.drop_table("assistant_run_events")
    op.drop_index("ix_assistant_runs_ws_created", table_name="assistant_runs")
    op.drop_table("assistant_runs")
