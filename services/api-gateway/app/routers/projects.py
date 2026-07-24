from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event
from daypilot_orchestrator.integrations.notifications import record_notification

from .. import repository, serializers
from ..db import get_session

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str
    goal: str = ""
    stack: str = ""
    repository: str = ""
    milestone: str = ""
    status: str = "Active"
    risk: str = "low"
    workspaceId: str = "default"


class UpdateProjectBody(BaseModel):
    name: str | None = None
    progress: int | None = None
    status: str | None = None
    risk: str | None = None
    nextHumanAction: str | None = None
    continueAction: str | None = None


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


@router.post("", status_code=201)
def create_project(body: CreateProjectBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Persist a project (and its first-milestone task) in one transaction, then
    emit a project.created event + a notification so Home, the planner, and the
    notification center all see it — the backend is the single source of truth."""
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Project name is required")
    project, tasks = repository.create_project(
        session, body.workspaceId, body.name,
        goal=body.goal, stack=body.stack, repository=body.repository,
        milestone=body.milestone, status=body.status, risk=body.risk,
    )
    session.add(Event(
        workspace_id=body.workspaceId, type="project.created",
        payload_json={"projectId": project.id, "name": project.name, "tasks": len(tasks)},
    ))
    record_notification(session, body.workspaceId, {
        "provider": "daypilot", "type": "project.created",
        "title": "Project created",
        "summary": f"“{project.name}” was created" + (f" with {len(tasks)} starter task." if tasks else "."),
        "severity": "info",
    })
    return {**serializers.serialize_project(project), "createdTasks": len(tasks)}


@router.get("/{project_id}")
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = repository.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return serializers.serialize_project(project)


@router.patch("/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    patch = {
        "name": body.name, "progress": body.progress, "status": body.status, "risk": body.risk,
        "next_human_action": body.nextHumanAction, "continue_action": body.continueAction,
    }
    project = repository.update_project(session, project_id, {k: v for k, v in patch.items() if v is not None})
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return serializers.serialize_project(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, session: Session = Depends(get_session)) -> None:
    if not repository.delete_project(session, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
