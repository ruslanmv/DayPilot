"""Shared pytest setup.

Points DayPilot services at an isolated temporary SQLite database and creates
the schema once per test session, so gateway domain tests exercise real
persistence without touching a developer's local database.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.mkdtemp(prefix="daypilot-test-")) / "daypilot_test.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB}")

# Create the schema on the configured test database before any app import
# triggers the (lru-cached) engine.
from daypilot_knowledge.db import Base, create_engine_from_settings  # noqa: E402

Base.metadata.create_all(create_engine_from_settings())
