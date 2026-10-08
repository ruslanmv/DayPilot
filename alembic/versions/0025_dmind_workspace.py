"""dmind workspace organisation: project association and tags (additive, nullable)."""
import sqlalchemy as sa
from alembic import op

revision = "0025_dmind_workspace"
down_revision = "0024_dmind_diagrams"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("diagrams") as batch:
        batch.add_column(sa.Column("project_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("tags_text", sa.String(1000), nullable=True))
    op.create_index("ix_diagrams_project_id", "diagrams", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_diagrams_project_id", table_name="diagrams")
    with op.batch_alter_table("diagrams") as batch:
        batch.drop_column("tags_text")
        batch.drop_column("project_id")
