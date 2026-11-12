"""HomePilot connector (additive): pairing requests, scoped grants, proposals."""
import sqlalchemy as sa
from alembic import op

revision = "0030_homepilot_connector"
down_revision = "0029_presentations_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepilot_pairings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_code", sa.String(16), nullable=False, unique=True, index=True),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("client_account_ref", sa.String(200), nullable=False),
        sa.Column("requested_scopes", sa.JSON(), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("granted_scopes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "homepilot_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("token_hint", sa.String(12), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("client_account_ref", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "homepilot_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("grant_id", sa.String(36), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("origin_ref", sa.String(200), nullable=False),
        sa.Column("capability", sa.String(80), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("approval_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ux_homepilot_proposal_idem", "homepilot_proposals",
                    ["grant_id", "idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_homepilot_proposal_idem", table_name="homepilot_proposals")
    op.drop_table("homepilot_proposals")
    op.drop_table("homepilot_grants")
    op.drop_table("homepilot_pairings")
