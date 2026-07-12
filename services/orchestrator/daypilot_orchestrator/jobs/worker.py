"""Job worker (batch B12).

Claims one runnable job, dispatches it to a registered handler for its kind, and
completes or fails it (with retry/backoff). `process_once` is deterministic and
unit-testable; a real deployment loops it across worker processes.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from daypilot_knowledge.db import Job

from . import queue

# kind -> handler(payload) -> result dict
HandlerFn = Callable[[dict[str, Any]], dict[str, Any]]


def process_once(session: Session, handlers: dict[str, HandlerFn], kinds: list[str] | None = None) -> Job | None:
    """Process a single job; returns the job or None if the queue was empty."""
    job = queue.claim_next(session, kinds=kinds)
    if job is None:
        return None
    handler = handlers.get(job.kind)
    if handler is None:
        return queue.fail(session, job, f"No handler registered for kind '{job.kind}'")
    try:
        result = handler(dict(job.payload_json or {}))
        return queue.complete(session, job, result)
    except Exception as exc:  # noqa: BLE001 - failures are recorded, not raised
        return queue.fail(session, job, f"{type(exc).__name__}: {exc}")


def drain(session: Session, handlers: dict[str, HandlerFn], max_jobs: int = 1000) -> int:
    """Process runnable jobs until the queue is empty or max_jobs is reached."""
    processed = 0
    while processed < max_jobs:
        job = process_once(session, handlers)
        if job is None:
            break
        processed += 1
    return processed
