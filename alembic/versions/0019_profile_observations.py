"""Consented-learning observations (AI profile, Phase 4).

Additive: ``user_profile_observations`` records learned preference *suggestions*.
No silent memory — an observation starts ``suggested`` and only a user-confirmed
one may enter model context; rejected ones suppress repeat suggestions. Declared
profile values always outrank a confirmed observation.

Revision ID: 0019_profile_observations
Revises: 0018_ai_profile
Create Date: 2026-07-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_profile_observations"
down_revision = "0018_ai_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profile_observations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default"),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default="inferred"),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="suggested"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_profile_obs_owner", "user_profile_observations",
                    ["user_id", "workspace_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_user_profile_obs_owner", table_name="user_profile_observations")
    op.drop_table("user_profile_observations")
