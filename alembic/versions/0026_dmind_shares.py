"""dmind read-only expiring share links (additive; nothing is shared by default)."""
import sqlalchemy as sa
from alembic import op

revision = "0026_dmind_shares"
down_revision = "0025_dmind_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagram_shares",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diagram_id", sa.String(36), sa.ForeignKey("diagrams.id"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("include_notes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_diagram_shares_diagram_id", "diagram_shares", ["diagram_id"])
    op.create_index("ix_diagram_shares_workspace_id", "diagram_shares", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_diagram_shares_workspace_id", table_name="diagram_shares")
    op.drop_index("ix_diagram_shares_diagram_id", table_name="diagram_shares")
    op.drop_table("diagram_shares")
