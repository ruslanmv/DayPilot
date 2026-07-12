"""Durable job queue (batch B12).

Revision ID: 0004_jobs_queue
Revises: 0003_document_versioning
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_jobs_queue"
down_revision = "0003_document_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("kind", sa.String(length=80), nullable=False, index=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_state_runafter", "jobs", ["state", "run_after"])


def downgrade() -> None:
    op.drop_index("ix_jobs_state_runafter", table_name="jobs")
    op.drop_table("jobs")
