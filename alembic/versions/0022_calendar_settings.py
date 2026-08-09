"""Calendar behaviour and meeting-context policy.

One additive table. ``calendar_settings`` holds, per workspace, how DayPilot
plans around connected calendars and — the part that matters most — the
allow-list of places a meeting brief may draw context from, plus what to do with
a calendar entry marked private.

Nothing existing is modified. Calendar connections themselves live in
``integration_connections`` like every other provider, and calendar writes keep
going through ``approvals`` — there is deliberately no column that could switch
that off.

Revision ID: 0022_calendar_settings
Revises: 0021_standup_copilot
Create Date: 2026-08-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_calendar_settings"
down_revision = "0021_standup_copilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        # meeting preparation
        sa.Column("prepare_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("prepare_scope", sa.String(length=20), nullable=False, server_default="important"),
        sa.Column("prep_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("auto_prep_blocks", sa.Boolean(), nullable=False, server_default="1"),
        # meeting context policy
        sa.Column("context_sources", sa.JSON(), nullable=False),
        sa.Column("private_events", sa.String(length=20), nullable=False,
                  server_default="metadata_only"),
        # planning
        sa.Column("accepted_are_fixed", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("ignore_declined", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("tentative_blocks", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_calendar_settings_workspace_id", "calendar_settings", ["workspace_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_settings_workspace_id", table_name="calendar_settings")
    op.drop_table("calendar_settings")
