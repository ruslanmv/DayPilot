"""Backend-owned knowledge sources (Issue 1).

The Settings → Knowledge sources screen lists real, persisted rows and its
buttons do real work: adding a local folder validates a path that exists on the
DayPilot server (a browser cannot hand the server an arbitrary local folder),
re-indexing enqueues a durable background job, and removing deletes the grant.
Box is offered honestly — only when the deployment has configured OAuth.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Job, KnowledgeSource
from daypilot_knowledge.db.models import utcnow


def _public(row: KnowledgeSource) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider": row.provider,
        "displayName": row.display_name,
        "location": row.location,
        "scope": row.scope,
        "permission": row.permission,
        "status": row.status,
        "projectIds": row.project_ids or [],
        "lastIndexedAt": row.last_indexed_at.isoformat() if row.last_indexed_at else None,
        "lastError": row.last_error,
    }


def list_sources(session: Session, workspace_id: str) -> dict[str, Any]:
    rows = session.execute(
        select(KnowledgeSource).where(KnowledgeSource.workspace_id == workspace_id)
        .order_by(KnowledgeSource.created_at.desc())
    ).scalars().all()
    return {"sources": [_public(r) for r in rows], "boxAvailable": _box_available()}


def _enqueue_index(session: Session, source: KnowledgeSource) -> str:
    """Re-index runs as a durable background job, not inside the HTTP request."""
    job = Job(
        workspace_id=source.workspace_id, kind="knowledge.reindex", state="queued",
        payload_json={"sourceId": source.id, "provider": source.provider, "location": source.location},
    )
    session.add(job)
    source.status = "queued"
    source.last_error = None
    session.flush()
    return job.id


def add_local(session: Session, workspace_id: str, path: str, display_name: str | None = None) -> dict[str, Any]:
    """Add a local folder by a server path that must actually exist. A web
    browser cannot safely hand the server an arbitrary local directory, so the
    contract is an explicit, validated server path."""
    path = (path or "").strip()
    if not path:
        return {"error": "path_required"}
    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        return {"error": "path_not_found", "detail": f"No folder at {path} on the DayPilot server."}
    source = KnowledgeSource(
        workspace_id=workspace_id, provider="local",
        display_name=(display_name or p.name or path), location=str(p),
        scope=str(p), permission="read_index", status="queued",
    )
    session.add(source)
    session.flush()
    job_id = _enqueue_index(session, source)
    return {"source": _public(source), "jobId": job_id}


def reindex(session: Session, workspace_id: str, source_id: str) -> dict[str, Any]:
    source = session.get(KnowledgeSource, source_id)
    if source is None or source.workspace_id != workspace_id:
        return {"error": "not_found"}
    job_id = _enqueue_index(session, source)
    return {"source": _public(source), "jobId": job_id}


def delete_source(session: Session, workspace_id: str, source_id: str) -> bool:
    source = session.get(KnowledgeSource, source_id)
    if source is None or source.workspace_id != workspace_id:
        return False
    session.delete(source)
    session.flush()
    return True


def source_jobs(session: Session, workspace_id: str, source_id: str) -> dict[str, Any]:
    rows = session.execute(
        select(Job).where(Job.workspace_id == workspace_id, Job.kind == "knowledge.reindex")
        .order_by(Job.created_at.desc()).limit(20)
    ).scalars().all()
    jobs = [{"id": j.id, "state": j.state, "createdAt": j.created_at.isoformat() if j.created_at else None,
             "lastError": j.last_error}
            for j in rows if (j.payload_json or {}).get("sourceId") == source_id]
    return {"jobs": jobs}


def _box_available() -> bool:
    return bool(os.getenv("BOX_OAUTH_CLIENT_ID"))


def box_oauth_start(workspace_id: str) -> dict[str, Any]:
    if not _box_available():
        return {"available": False, "reason": "box_not_configured",
                "message": "Box isn't configured on this deployment. Add BOX_OAUTH_CLIENT_ID to enable it."}
    return {"available": True}


def _now() -> Any:
    return utcnow()
