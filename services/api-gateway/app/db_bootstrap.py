"""Automatic schema bootstrap so a fresh install just works.

The single biggest first-run failure is starting the API before applying
migrations — every request then dies with "no such table: users". To make
`make run` (and a bare `uvicorn`, and the Docker image) work with zero manual
steps, the gateway brings the database schema up to date on startup:

  1. Try Alembic `upgrade head` (keeps migration history intact).
  2. If Alembic can't run for any reason, fall back to `create_all` so the app
     still has its tables (the local-first SQLite default should never be left
     unusable).

Set DAYPILOT_AUTO_MIGRATE=0 to opt out (e.g. a managed production deployment
that runs migrations as a separate, gated release step).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("daypilot.db_bootstrap")


def _repo_root() -> Path:
    # services/api-gateway/app/db_bootstrap.py -> repo root is parents[3].
    here = Path(__file__).resolve()
    for parent in [here.parents[3], *here.parents]:
        if (parent / "alembic.ini").exists():
            return parent
    return here.parents[3]


def _enabled() -> bool:
    return os.getenv("DAYPILOT_AUTO_MIGRATE", "1").lower() not in ("0", "false", "no", "off")


def ensure_schema() -> str:
    """Bring the database schema up to date. Returns a short status string.

    Safe to call on every startup: Alembic upgrade is idempotent, and the
    create_all fallback only adds missing tables. It NEVER raises (catches even
    BaseException) so a schema hiccup can't crash application startup — the app
    still comes up and surfaces a health endpoint.

    The Alembic Config is built WITHOUT an ini file on purpose: our env.py calls
    logging.config.fileConfig(config_file_name) when one is present, which
    disables the already-configured (uvicorn) loggers and, running a second time
    inside the server's lifespan, has caused startup failures. Building the
    Config programmatically (script_location + url only) skips that entirely.
    """
    if not _enabled():
        return "skipped"

    try:
        from daypilot_knowledge.db import get_database_url
        # Make sure Alembic's env.py and the app agree on the database URL.
        url = get_database_url()
        os.environ.setdefault("DATABASE_URL", url)
    except BaseException as exc:  # noqa: BLE001 - never let bootstrap crash startup
        logger.error("Could not resolve the database URL: %s", exc)
        return "failed"

    try:
        from alembic import command
        from alembic.config import Config

        # No ini file → env.py won't run fileConfig() and won't touch logging.
        cfg = Config()
        cfg.set_main_option("script_location", str(_repo_root() / "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        logger.info("Database schema is up to date (alembic upgrade head).")
        return "migrated"
    except BaseException as exc:  # noqa: BLE001 - fall back rather than crash
        logger.warning("Alembic upgrade failed (%s); falling back to create_all.", exc)

    try:
        from daypilot_knowledge.db import Base, create_engine_from_settings

        Base.metadata.create_all(create_engine_from_settings(url))
        logger.info("Database schema ensured via create_all fallback.")
        return "created"
    except BaseException as exc:  # noqa: BLE001 - last resort; log and continue
        logger.error("Could not ensure database schema: %s", exc)
        return "failed"
