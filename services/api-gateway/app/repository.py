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


def get_agent_run(session: Session, run_id: str) -> AgentRun | None:
    return session.get(AgentRun, run_id)
