"""Production-readiness: zero-step startup and single-origin serving.

Locks in the two fixes that make a fresh install "just work":
  * The gateway auto-applies the schema on startup, so a first run never dies
    with "no such table: users" (the exact first-run crash).
  * With a web build present, the gateway serves the SPA at `/` and accepts the
    browser's same-origin `/api/...` calls — one process, one port — while
    direct `/v1/...` still works for internal callers and tests.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.db_bootstrap import ensure_schema


def test_ensure_schema_creates_tables_on_fresh_db(monkeypatch) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dp-boot-")) / f"{uuid.uuid4().hex}.db"
    url = f"sqlite:///{tmp}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DAYPILOT_AUTO_MIGRATE", "1")

    status = ensure_schema()
    assert status in ("migrated", "created")

    tables = set(inspect(create_engine(url)).get_table_names())
    # The tables whose absence caused the reported first-run 500s.
    assert "users" in tables and "mailbox_connections" in tables


def test_ensure_schema_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("DAYPILOT_AUTO_MIGRATE", "0")
    assert ensure_schema() == "skipped"


def test_ensure_schema_does_not_disable_existing_loggers(monkeypatch) -> None:
    """Regression: the in-process migration must NOT run alembic's fileConfig,
    which disables already-configured (uvicorn) loggers and broke `make start`
    on some systems. Building the Alembic Config without an ini file avoids it,
    so a logger created before ensure_schema stays enabled afterward."""
    import logging
    import tempfile
    import uuid
    from pathlib import Path

    probe = logging.getLogger("daypilot.test.logger-probe")
    probe.disabled = False
    tmp = Path(tempfile.mkdtemp(prefix="dp-log-")) / f"{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp}")
    monkeypatch.setenv("DAYPILOT_AUTO_MIGRATE", "1")

    ensure_schema()

    assert probe.disabled is False  # fileConfig(disable_existing_loggers) never ran


def test_api_prefix_strip_and_direct_paths_coexist() -> None:
    # A stale/misconfigured proxy is no longer required: same-origin `/api/...`
    # reaches the API, and direct `/v1/...` is untouched.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/api/health").json().get("ok") is True
        assert client.get("/api/v1/auth/config").status_code == 200
        assert client.get("/v1/auth/config").status_code == 200


def test_startup_bootstraps_schema_via_testclient() -> None:
    # Entering the TestClient context fires startup events; the app must be
    # usable immediately (schema present) without a manual migrate step.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/v1/email/status").status_code == 200
