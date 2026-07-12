"""Integration job worker glue (batch I1).

Bridges approved integration actions to the durable job worker: it promotes
approved (gated) jobs to `queued`, then drains them through a handler that
performs the provider call. A deployment loops `run_pending` across worker
processes; it is also directly callable and deterministic for tests.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from ..jobs.worker import drain
from . import service


def integration_handlers(session: Session) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {"integration.execute": lambda payload: service.execute_job_payload(session, payload)}


def run_pending(session: Session, max_jobs: int = 100) -> int:
    """Promote approved integration actions, then run them. Returns how many
    jobs were processed."""
    service.promote_approved_actions(session)
    return drain(session, integration_handlers(session), max_jobs=max_jobs)
