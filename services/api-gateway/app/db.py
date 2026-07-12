"""Database access for the API gateway.

Reuses the shared SQLAlchemy models and engine defined by the knowledge
service so every DayPilot service speaks to one schema and one migration
history (alembic).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from daypilot_knowledge.db import create_engine_from_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine_from_settings()


@lru_cache(maxsize=1)
def _get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = _get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
