from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Job
from daypilot_orchestrator.jobs import queue
from daypilot_orchestrator.scale.retention import sweep

from ..db import get_session
from ..pagination import keyset_page, page_response
from ..rbac import require_operator

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


class EnqueueBody(BaseModel):
    kind: str
    payload: dict[str, Any] = {}
    workspaceId: str = "default"
    maxAttempts: int = 3
    priority: int = 0


@router.get("")
def list_jobs(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    state: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(Job).where(Job.workspace_id == workspaceId)
    if state:
        stmt = stmt.where(Job.state == state)
    rows, next_cursor = keyset_page(
        session, stmt, model=Job, sort_field="created_at", order="desc",
        cursor=cursor, limit=limit, allowed_sort_fields=("created_at", "updated_at"),
    )
    return page_response([queue.serialize(r) for r in rows], next_cursor, limit)


@router.post("", status_code=201)
def enqueue(body: EnqueueBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = queue.enqueue(
        session, body.kind, body.payload, body.workspaceId, body.maxAttempts, body.priority
    )
    return queue.serialize(job)


@router.get("/{job_id}")
def get_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return queue.serialize(job)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = queue.cancel(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return queue.serialize(job)


@router.post("/retention/sweep")
def retention_sweep(session: Session = Depends(get_session), _p=Depends(require_operator)) -> dict[str, Any]:
    return sweep(session)
