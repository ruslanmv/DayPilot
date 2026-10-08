"""Presentations extensions (additive): SVG source links, opt-in schedules, imported templates, expert builders."""
import sqlalchemy as sa
from alembic import op

revision = "0029_presentations_extensions"
down_revision = "0028_presentations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("presentation_assets") as batch:
        batch.add_column(sa.Column("source_asset_id", sa.String(36), nullable=True))
    with op.batch_alter_table("presentation_revisions") as batch:
        batch.add_column(sa.Column("expert_script", sa.Text(), nullable=True))
    with op.batch_alter_table("presentation_series") as batch:
        batch.add_column(sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_result", sa.String(300), nullable=True))
    op.create_index("ix_presentation_series_next_run_at", "presentation_series", ["next_run_at"])
    op.create_table(
        "presentation_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("presentation_companies.id"), nullable=False, index=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("presentation_templates")
    op.drop_index("ix_presentation_series_next_run_at", table_name="presentation_series")
    with op.batch_alter_table("presentation_series") as batch:
        batch.drop_column("last_result")
        batch.drop_column("last_fired_at")
        batch.drop_column("next_run_at")
        batch.drop_column("schedule_enabled")
    with op.batch_alter_table("presentation_revisions") as batch:
        batch.drop_column("expert_script")
    with op.batch_alter_table("presentation_assets") as batch:
        batch.drop_column("source_asset_id")
