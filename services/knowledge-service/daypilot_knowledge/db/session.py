from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    default_path = Path("local_data/sqlite/daypilot.db")
    default_path.parent.mkdir(parents=True, exist_ok=True)
    return os.getenv("DATABASE_URL", f"sqlite:///{default_path}")


def create_engine_from_settings(url: str | None = None) -> Engine:
    database_url = url or get_database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    local_engine = engine or create_engine_from_settings()
    SessionLocal = sessionmaker(bind=local_engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
