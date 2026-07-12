"""Version-safe document outputs (batch B10).

Adds parent/version/is_generated to documents so AI-generated outputs are stored
as new versions that reference the original, which is never modified.

Revision ID: 0003_document_versioning
Revises: 0002_daypilot_domain
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_document_versioning"
down_revision = "0002_daypilot_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("parent_document_id", sa.String(length=36), nullable=True))
    op.add_column("documents", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("documents", sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_documents_parent", "documents", ["parent_document_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_parent", table_name="documents")
    op.drop_column("documents", "is_generated")
    op.drop_column("documents", "version")
    op.drop_column("documents", "parent_document_id")
