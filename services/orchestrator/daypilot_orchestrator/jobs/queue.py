"""Durable job queue (batch B12).

DB-backed so it works local-first with no external broker, while presenting the
same contract a Redis/arq worker would: durable state, retries with exponential
backoff, cancellation, and dead-lettering. A production deployment can swap the
storage without changing callers.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Job

BACKOFF_BASE_SECONDS = 2


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    workspace_id: str = "default",
    max_attempts: int = 3,
    priority: int = 0,
) -> Job:
    job = Job(
        workspace_id=workspace_id,
        kind=kind,
        payload_json=payload or {},
        state="queued",
        max_attempts=max_attempts,
        priority=priority,
        run_after=datetime.utcnow(),
    )
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session, kinds: list[str] | None = None) -> Job | None:
    """Claim the next runnable job (queued and due), marking it running."""
    now = datetime.utcnow()
    stmt = select(Job).where(
        Job.state == "queued",
        (Job.run_after.is_(None)) | (Job.run_after <= now),
    )
    if kinds:
        stmt = stmt.where(Job.kind.in_(kinds))
    stmt = stmt.order_by(Job.priority.desc(), Job.created_at.asc()).limit(1)
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    job.state = "running"
    job.attempts += 1
    job.updated_at = now
    session.flush()
    return job


def complete(session: Session, job: Job, result: dict[str, Any] | None = None) -> Job:
    job.state = "succeeded"
    job.result_json = result or {}
    job.updated_at = datetime.utcnow()
    session.flush()
    return job


def fail(session: Session, job: Job, error: str) -> Job:
    """Fail a job: retry with exponential backoff, or dead-letter if exhausted."""
    job.last_error = error[:2000]
    if job.attempts >= job.max_attempts:
        job.state = "dead_letter"
    else:
        delay = BACKOFF_BASE_SECONDS ** job.attempts
        job.state = "queued"
        job.run_after = datetime.utcnow() + timedelta(seconds=delay)
    job.updated_at = datetime.utcnow()
    session.flush()
    return job


def cancel(session: Session, job_id: str) -> Job | None:
    job = session.get(Job, job_id)
    if job is None:
        return None
    if job.state in {"queued", "running"}:
        job.state = "cancelled"
        job.updated_at = datetime.utcnow()
        session.flush()
    return job


def serialize(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "workspaceId": job.workspace_id,
        "kind": job.kind,
        "state": job.state,
        "attempts": job.attempts,
        "maxAttempts": job.max_attempts,
        "lastError": job.last_error,
        "result": job.result_json,
        "runAfter": job.run_after.isoformat() if job.run_after else None,
    }
