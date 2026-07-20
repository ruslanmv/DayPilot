"""Identity & login: local accounts, workspaces, memberships, sessions.

Additive. Adds password/status/mfa columns to `users` and five new tables
(`workspaces`, `workspace_memberships`, `auth_sessions`, `external_identities`,
`auth_events`). No secrets are stored: only scrypt password hashes and the
SHA-256 of session tokens.

Revision ID: 0008_identity
Revises: 0007_chat_sessions
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_identity"
down_revision = "0007_chat_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=300), nullable=True))
    op.add_column("users", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("users", sa.Column("mfa_state", sa.String(length=20), nullable=False, server_default="none"))

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, server_default="My workspace"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_membership_user_ws", "workspace_memberships", ["user_id", "workspace_id"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("issuer", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("secret_reference", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extid_issuer_subject", "external_identities", ["issuer", "subject"], unique=True)

    op.create_table(
        "auth_events",
        sa.Column("seq", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("email", sa.String(length=320), nullable=True, index=True),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_authevent_email_created", "auth_events", ["email", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_authevent_email_created", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_index("ix_extid_issuer_subject", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_table("auth_sessions")
    op.drop_index("ix_membership_user_ws", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
    op.drop_column("users", "mfa_state")
    op.drop_column("users", "status")
    op.drop_column("users", "password_hash")
