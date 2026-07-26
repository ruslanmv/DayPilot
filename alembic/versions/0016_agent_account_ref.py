"""Bind each HomePilot agent link to its account (multi-account security).

Additive: ``homepilot_agent_links.account_ref`` records the HomePilot account a
synced agent belongs to (``user:<id>`` for a per-user connection, ``shared`` for
the shared instance key, or a stable credential fingerprint for an older
HomePilot without the identity endpoint). DayPilot stamps every link with the
connection's bound account so one user's agents can never blend with another's;
if the bound account changes, links from the previous account are marked offline
rather than mixed. Existing rows default to an empty ref.

Revision ID: 0016_agent_account_ref
Revises: 0015_agent_task_mapping
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_agent_account_ref"
down_revision = "0015_agent_task_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "homepilot_agent_links",
        sa.Column("account_ref", sa.String(length=200), nullable=False, server_default=""),
    )
    op.create_index("ix_homepilot_link_account", "homepilot_agent_links", ["account_ref"])


def downgrade() -> None:
    op.drop_index("ix_homepilot_link_account", table_name="homepilot_agent_links")
    op.drop_column("homepilot_agent_links", "account_ref")
