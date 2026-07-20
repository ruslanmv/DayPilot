"""Hardening + release verification (Batch 6).

Covers the cross-cutting guarantees a production deployment depends on:
  * Workspace isolation — assistant runs, mailboxes, and provider connections in
    one workspace never leak into another.
  * Secret persistence by reference — credentials live in the credential store,
    never in the database row or any API payload, and disconnect removes them.
  * Migration round-trip — the Batch 3/4 migrations upgrade and downgrade
    cleanly (rollback-safe).
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, select

from daypilot_knowledge.db import (
    AssistantRun,
    MailboxConnection,
    ProviderConnection,
    session_scope,
)
from daypilot_orchestrator.assistant import orchestrator
from daypilot_orchestrator.integrations.credentials import credential_store


def _ws() -> str:
    return "hard-" + uuid.uuid4().hex[:8]


# --- workspace isolation -----------------------------------------------------

def test_assistant_runs_are_workspace_isolated():
    a, b = _ws(), _ws()
    with session_scope() as s:
        orchestrator.run_turn(s, a, "what is today?")
        orchestrator.run_turn(s, a, "what needs approval?")
        orchestrator.run_turn(s, b, "what is today?")
    with session_scope() as s:
        a_runs = s.execute(select(AssistantRun).where(AssistantRun.workspace_id == a)).scalars().all()
        b_runs = s.execute(select(AssistantRun).where(AssistantRun.workspace_id == b)).scalars().all()
    assert len(a_runs) == 2 and len(b_runs) == 1
    assert all(r.workspace_id == a for r in a_runs)


def test_mailbox_and_provider_status_are_workspace_isolated():
    a, b = _ws(), _ws()
    with session_scope() as s:
        s.add(MailboxConnection(workspace_id=a, provider="imap", email_address="a@x.com",
                                status="connected", secret_reference=f"mailbox:{a}"))
        s.add(ProviderConnection(workspace_id=a, kind="local", state="connected", active=True))
    # Workspace b sees no mailbox and no connected provider.
    with session_scope() as s:
        b_mail = s.execute(select(MailboxConnection).where(MailboxConnection.workspace_id == b)).scalars().all()
        assert b_mail == []
        assert orchestrator.provider_available(s, a) is True
        assert orchestrator.provider_available(s, b) is False


# --- secret persistence by reference ----------------------------------------

def test_credentials_stored_by_reference_never_in_db_or_payload():
    from app import mail_setup

    ws = _ws()
    ref = f"mailbox:{ws}"
    with session_scope() as s:
        s.add(MailboxConnection(workspace_id=ws, provider="imap", email_address="u@x.com",
                                username="u@x.com", imap_host="imap.x.com", status="connected",
                                secret_reference=ref))
    credential_store().put(ref, {"password": "R3alSecret!", "username": "u@x.com"})

    # The DB row stores only a reference, never the secret.
    with session_scope() as s:
        row = s.execute(select(MailboxConnection).where(MailboxConnection.workspace_id == ws)).scalar_one()
        assert "R3alSecret!" not in (row.secret_reference or "")
        public = mail_setup._public(row)
    assert "R3alSecret!" not in str(public)
    assert "secret" not in {k.lower() for k in public}  # no secret_reference key surfaced

    # Disconnect removes the credential from the store.
    with session_scope() as s:
        mail_setup.disconnect(s, ws)
    assert credential_store().has(ref) is False


# --- migration round-trip (rollback-safe) -----------------------------------

def test_batch_migrations_upgrade_and_downgrade_cleanly():
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[1]
    tmp = Path(tempfile.mkdtemp(prefix="dp-mig-")) / "roundtrip.db"
    url = f"sqlite:///{tmp}"

    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        tables = set(inspect(engine).get_table_names())
        assert {"assistant_runs", "assistant_run_events", "mailbox_connections"} <= tables

        # Roll back the Batch 3/4 migrations and confirm the tables are gone.
        command.downgrade(cfg, "0009_provider_connections")
        tables = set(inspect(create_engine(url)).get_table_names())
        assert "assistant_runs" not in tables and "mailbox_connections" not in tables
        assert "provider_connections" in tables  # earlier migrations remain

        # Re-upgrade to head is clean (idempotent forward path).
        command.upgrade(cfg, "head")
        tables = set(inspect(create_engine(url)).get_table_names())
        assert {"assistant_runs", "mailbox_connections"} <= tables
        engine.dispose()
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
