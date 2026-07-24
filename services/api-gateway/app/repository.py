"""Query builders for DayPilot domain list endpoints.

Each `list_*` helper applies allowlisted server-side filters and hands the
statement to the keyset paginator, returning a ready-to-serialize page.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AgentRun,
    Approval,
    Document,
    Project,
    Task,
)

from . import serializers
from .pagination import keyset_page, page_response

DEFAULT_WORKSPACE = "default"
TIME_SORTS = ("created_at", "updated_at")


def _paginate(
    session: Session,
    stmt: Any,
    *,
    model: Any,
    serialize: Callable[[Any], dict[str, Any]],
    sort: str,
    order: str,
    cursor: str | None,
    limit: int,
    allowed_sort_fields=TIME_SORTS,
) -> dict[str, Any]:
    rows, next_cursor = keyset_page(
        session,
        stmt,
        model=model,
        sort_field=sort,
        order=order,
        cursor=cursor,
        limit=limit,
        allowed_sort_fields=allowed_sort_fields,
    )
    return page_response([serialize(r) for r in rows], next_cursor, limit)


def list_tasks(
    session: Session,
    *,
    workspace_id: str = DEFAULT_WORKSPACE,
    owner: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    priority: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Task).where(Task.workspace_id == workspace_id)
    if owner:
        stmt = stmt.where(Task.owner == owner)
    if status:
        stmt = stmt.where(Task.status == status)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    return _paginate(
        session, stmt, model=Task, serialize=serializers.serialize_task,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


def list_projects(
    session: Session,
    *,
    workspace_id: str = DEFAULT_WORKSPACE,
    status: str | None = None,
    risk: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Project).where(Project.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Project.status == status)
    if risk:
        stmt = stmt.where(Project.risk == risk)
    return _paginate(
        session, stmt, model=Project, serialize=serializers.serialize_project,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


def list_agent_runs(
    session: Session,
    *,
    workspace_id: str = DEFAULT_WORKSPACE,
    state: str | None = None,
    status: str | None = None,
    project_id: str | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(AgentRun).where(AgentRun.workspace_id == workspace_id)
    if state:
        stmt = stmt.where(AgentRun.state == state)
    if status:
        stmt = stmt.where(AgentRun.display_status == status)
    if project_id:
        stmt = stmt.where(AgentRun.project_id == project_id)
    return _paginate(
        session, stmt, model=AgentRun, serialize=serializers.serialize_agent_run,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


def list_documents(
    session: Session,
    *,
    project_id: str | None = None,
    status: str | None = None,
    source: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Document)
    if project_id:
        stmt = stmt.where(Document.project_id == project_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if source:
        stmt = stmt.where(Document.source == source)
    # documents has created_at only (no updated_at column).
    return _paginate(
        session, stmt, model=Document, serialize=serializers.serialize_document,
        sort=sort, order=order, cursor=cursor, limit=limit,
        allowed_sort_fields=("created_at",),
    )


def list_approvals(
    session: Session,
    *,
    workspace_id: str = DEFAULT_WORKSPACE,
    status: str | None = None,
    risk: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Approval).where(Approval.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(Approval.status == status)
    if risk:
        stmt = stmt.where(Approval.risk == risk)
    return _paginate(
        session, stmt, model=Approval, serialize=serializers.serialize_approval,
        sort=sort, order=order, cursor=cursor, limit=limit,
        allowed_sort_fields=("created_at",),
    )


def get_task(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def get_project(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


# --- Project mutations (Issue 4: persistent, server-owned projects) ----------

_PROJECT_EDITABLE = {
    "name", "progress", "status", "risk", "ai_activity", "next_human_action",
    "continue_action", "due_date", "ai_actions", "linked_sources",
}


def create_project(
    session: Session,
    workspace_id: str,
    name: str,
    *,
    goal: str = "",
    stack: str = "",
    repository: str = "",
    milestone: str = "",
    status: str = "Active",
    risk: str = "low",
) -> tuple[Project, list[Task]]:
    """Create a project and its initial actionable task(s) in one transaction.

    Returns (project, created_tasks). The caller emits the project.created event
    and notification so the whole thing is one atomic unit of work."""
    from daypilot_knowledge.db import Project as _Project, Task as _Task  # local import keeps module import light

    linked: list[dict[str, Any]] = []
    if repository:
        linked.append({"kind": "repository", "ref": repository})

    project = _Project(
        workspace_id=workspace_id,
        name=name.strip(),
        status=status,
        risk=risk,
        progress=0,
        ai_activity="",
        next_human_action=(f"Kick off: {milestone}" if milestone else "Define the first milestone"),
        continue_action=(milestone or goal or "Plan the first steps"),
        ai_actions=[],
        linked_sources=linked,
    )
    session.add(project)
    session.flush()

    tasks: list[Task] = []
    # The first milestone becomes a real, actionable task so the project can
    # immediately contribute to planner readiness (Issue 2 + 4).
    if milestone.strip():
        task = _Task(
            workspace_id=workspace_id,
            title=milestone.strip(),
            owner="you",
            status="active",
            priority="high",
            source="project",
            project_id=project.id,
            context=(goal or f"First milestone for {name}."),
        )
        session.add(task)
        tasks.append(task)
    session.flush()
    return project, tasks


def update_project(session: Session, project_id: str, patch: dict[str, Any]) -> Project | None:
    project = session.get(Project, project_id)
    if project is None:
        return None
    for key, value in patch.items():
        if key in _PROJECT_EDITABLE and value is not None:
            setattr(project, key, value)
    session.flush()
    return project


def delete_project(session: Session, project_id: str) -> bool:
    project = session.get(Project, project_id)
    if project is None:
        return False
    # Detach tasks so a deleted project doesn't orphan FK references.
    for task in session.execute(select(Task).where(Task.project_id == project_id)).scalars():
        task.project_id = None
    session.delete(project)
    session.flush()
    return True


def get_agent_run(session: Session, run_id: str) -> AgentRun | None:
    return session.get(AgentRun, run_id)
