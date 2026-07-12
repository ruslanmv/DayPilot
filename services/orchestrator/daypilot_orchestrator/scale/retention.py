"""Retention sweeps (batch B12).

Bounds unbounded growth of high-volume, low-value rows — events (the Today
Context stream), succeeded/dead-letter jobs, and audit logs — by age. Generated
document outputs are retained (they are user artifacts); temporary chunks of
superseded generated versions can be swept. Configurable via env.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from daypilot_knowledge.db import AuditLog, Event, Job


def _cutoff(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


def sweep(session: Session) -> dict[str, Any]:
    event_days = int(os.getenv("DAYPILOT_RETENTION_EVENT_DAYS", "30"))
    job_days = int(os.getenv("DAYPILOT_RETENTION_JOB_DAYS", "14"))
    audit_days = int(os.getenv("DAYPILOT_RETENTION_AUDIT_DAYS", "365"))

    events_deleted = session.execute(
        delete(Event).where(Event.created_at < _cutoff(event_days))
    ).rowcount
    jobs_deleted = session.execute(
        delete(Job).where(
            Job.state.in_(("succeeded", "dead_letter", "cancelled")),
            Job.updated_at < _cutoff(job_days),
        )
    ).rowcount
    audit_deleted = session.execute(
        delete(AuditLog).where(AuditLog.created_at < _cutoff(audit_days))
    ).rowcount
    session.flush()
    return {
        "eventsDeleted": int(events_deleted or 0),
        "jobsDeleted": int(jobs_deleted or 0),
        "auditDeleted": int(audit_deleted or 0),
        "policy": {"eventDays": event_days, "jobDays": job_days, "auditDays": audit_days},
    }
