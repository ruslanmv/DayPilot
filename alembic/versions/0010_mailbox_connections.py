"""Backend-owned mailbox connections (Batch 3).

Additive: a `mailbox_connections` table so the backend — not the browser —
owns real mail connection state (Gmail/Microsoft OAuth or generic IMAP/SMTP).
Only safe metadata is stored; passwords/OAuth tokens live in the credential
store by `secret_reference` and are never stored, returned, or logged.

Revision ID: 0010_mailbox_connections
Revises: 0009_provider_connections
Create Date: 2026-07-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010_mailbox_connections"
down_revision = "0009_provider_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailbox_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, server_default="default", index=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("username", sa.String(length=320), nullable=True),
        sa.Column("imap_host", sa.String(length=255), nullable=True),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("imap_security", sa.String(length=10), nullable=False, server_default="ssl"),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_security", sa.String(length=10), nullable=False, server_default="starttls"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unconfigured"),
        sa.Column("secret_reference", sa.String(length=200), nullable=True),
        sa.Column("oauth_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mailbox_ws", "mailbox_connections", ["workspace_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_mailbox_ws", table_name="mailbox_connections")
    op.drop_table("mailbox_connections")
