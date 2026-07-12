from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Task

from .. import repository, serializers
from ..db import get_session

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    owner: str = "you"
    executor: str = ""
    priority: str = "medium"
    status: str = "active"
    day: str | None = None
    start: str | None = None
    end: str | None = None
    context: str | None = None
    source: str | None = None
    projectId: str | None = None
    workspaceId: str = "default"


@router.get("")
def list_tasks(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    owner: str | None = None,
    status: str | None = None,
    projectId: str | None = None,
    priority: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return repository.list_tasks(
        session, workspace_id=workspaceId, owner=owner, status=status,
        project_id=projectId, priority=priority, sort=sort, order=order,
        cursor=cursor, limit=limit,
    )


@router.get("/{task_id}")
def get_task(task_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = repository.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return serializers.serialize_task(task)


@router.post("", status_code=201)
def create_task(body: TaskCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    task = Task(
        workspace_id=body.workspaceId,
        title=body.title,
        owner=body.owner,
        executor=body.executor,
        priority=body.priority,
        status=body.status,
        day=body.day,
        start_time=body.start,
        end_time=body.end,
        context=body.context,
        source=body.source,
        project_id=body.projectId,
    )
    session.add(task)
    session.flush()
    return serializers.serialize_task(task)
