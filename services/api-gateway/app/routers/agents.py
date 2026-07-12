from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import repository, serializers
from ..db import get_session

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("")
def list_agent_runs(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    state: str | None = None,
    status: str | None = None,
    projectId: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return repository.list_agent_runs(
        session, workspace_id=workspaceId, state=state, status=status,
        project_id=projectId, sort=sort, order=order, cursor=cursor, limit=limit,
    )


@router.get("/{run_id}")
def get_agent_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = repository.get_agent_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return serializers.serialize_agent_run(run)
