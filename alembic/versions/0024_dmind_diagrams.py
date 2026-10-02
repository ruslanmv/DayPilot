"""Add isolated dmind graph heads and append-only revision snapshots."""
import sqlalchemy as sa
from alembic import op

revision = "0024_dmind_diagrams"
down_revision = "0023_slack_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diagrams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_diagrams_workspace_id", "diagrams", ["workspace_id"])
    op.create_table(
        "diagram_revisions",
        sa.Column("diagram_id", sa.String(36), sa.ForeignKey("diagrams.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("diagram_revisions")
    op.drop_index("ix_diagrams_workspace_id", table_name="diagrams")
    op.drop_table("diagrams")
