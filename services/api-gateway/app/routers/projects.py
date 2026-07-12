from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import repository, serializers
from ..db import get_session

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.get("")
def list_projects(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    status: str | None = None,
    risk: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return repository.list_projects(
        session, workspace_id=workspaceId, status=status, risk=risk,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


@router.get("/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = repository.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return serializers.serialize_project(project)
