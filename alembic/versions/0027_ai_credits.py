"""AI credits ledger (additive): per-workspace balance and an append-only event log."""
import sqlalchemy as sa
from alembic import op

revision = "0027_ai_credits"
down_revision = "0026_dmind_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_credit_accounts",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_allowance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period", sa.String(7), nullable=False, server_default=""),
    )
    op.create_table(
        "ai_credit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("action", sa.String(40), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_credit_events_workspace_id", "ai_credit_events", ["workspace_id"])
    op.create_index("ix_ai_credit_events_created_at", "ai_credit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_credit_events_created_at", table_name="ai_credit_events")
    op.drop_index("ix_ai_credit_events_workspace_id", table_name="ai_credit_events")
    op.drop_table("ai_credit_events")
    op.drop_table("ai_credit_accounts")
