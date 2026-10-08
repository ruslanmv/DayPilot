"""Presentations (additive): companies, immutable brand kits/assets, decks, revisions, runs, artifacts, weekly series."""
import sqlalchemy as sa
from alembic import op

revision = "0028_presentations"
down_revision = "0027_ai_credits"
branch_labels = None
depends_on = None

TS = dict(nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "presentation_companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active_brand_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_table(
        "presentation_brand_kits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("presentation_companies.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kit_json", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "version", name="uq_presentation_brand_kit_version"),
    )
    op.create_table(
        "presentation_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("presentation_companies.id"), nullable=False, index=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(40), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "sha256", name="uq_presentation_asset_hash"),
    )
    op.create_table(
        "presentation_decks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("presentation_companies.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("head_revision", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("series_id", sa.String(36), nullable=True, index=True),
        sa.Column("period_key", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_table(
        "presentation_revisions",
        sa.Column("deck_id", sa.String(36), sa.ForeignKey("presentation_decks.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("parent_revision", sa.Integer(), nullable=True),
        sa.Column("brand_version", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(20), nullable=False),
        sa.Column("storyline_json", sa.JSON(), nullable=False),
        sa.Column("locks_json", sa.JSON(), nullable=False),
        sa.Column("deck_json", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("pptx_sha256", sa.String(64), nullable=True),
        sa.Column("slide_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("approved_by", sa.String(120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "presentation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("deck_id", sa.String(36), nullable=False, index=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("epoch", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "presentation_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("deck_id", sa.String(36), nullable=False, index=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("store_key", sa.String(200), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "presentation_series",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("presentation_companies.id"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recipe_json", sa.JSON(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), **TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **TS),
    )
    op.create_table(
        "presentation_occurrences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("series_id", sa.String(36), sa.ForeignKey("presentation_series.id"), nullable=False, index=True),
        sa.Column("recipe_version", sa.Integer(), nullable=False),
        sa.Column("period_key", sa.String(60), nullable=False),
        sa.Column("period_start", sa.String(40), nullable=False),
        sa.Column("period_end", sa.String(40), nullable=False),
        sa.Column("deck_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("series_id", "recipe_version", "period_key", name="uq_presentation_occurrence"),
    )


def downgrade() -> None:
    for table in (
        "presentation_occurrences", "presentation_series", "presentation_artifacts", "presentation_runs",
        "presentation_revisions", "presentation_decks", "presentation_assets", "presentation_brand_kits",
        "presentation_companies",
    ):
        op.drop_table(table)
