"""AI profile & first-run onboarding — durable foundation (Phase 1).

Additive: three tenant-scoped tables give DayPilot a server-owned AI profile
(distinct from a HomePilot persona), profile-level goals, and first-run
progress. Completion moves off device-scoped ``localStorage`` and becomes a
server fact; work preferences may differ per workspace, so ownership is
``(user_id, workspace_id)``. No table stores provider credentials, mailbox
secrets, raw documents, or conversation history.

Revision ID: 0018_ai_profile
Revises: 0017_agent_delegations
Create Date: 2026-07-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0018_ai_profile"
down_revision = "0017_agent_delegations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_ai_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("locale", sa.String(length=35), nullable=True),
        sa.Column("preferred_name", sa.String(length=120), nullable=True),
        sa.Column("pronouns", sa.String(length=40), nullable=True),
        sa.Column("use_cases_json", sa.JSON(), nullable=True),
        sa.Column("schedule_json", sa.JSON(), nullable=True),
        sa.Column("planning_json", sa.JSON(), nullable=True),
        sa.Column("communication_json", sa.JSON(), nullable=True),
        sa.Column("accessibility_json", sa.JSON(), nullable=True),
        sa.Column("boundaries_json", sa.JSON(), nullable=True),
        sa.Column("category_consent_json", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_ai_profiles_owner", "user_ai_profiles",
                    ["user_id", "workspace_id"], unique=True)

    op.create_table(
        "user_profile_goals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_profile_goals_owner", "user_profile_goals",
                    ["user_id", "workspace_id", "status"])

    op.create_table(
        "onboarding_progress",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("flow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_started"),
        sa.Column("current_step", sa.String(length=40), nullable=False, server_default="welcome"),
        sa.Column("completed_steps_json", sa.JSON(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_onboarding_progress_owner", "onboarding_progress",
                    ["user_id", "workspace_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_onboarding_progress_owner", table_name="onboarding_progress")
    op.drop_table("onboarding_progress")
    op.drop_index("ix_user_profile_goals_owner", table_name="user_profile_goals")
    op.drop_table("user_profile_goals")
    op.drop_index("ix_user_ai_profiles_owner", table_name="user_ai_profiles")
    op.drop_table("user_ai_profiles")
