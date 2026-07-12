"""Today Context engine and day-plan lifecycle operations (batch B4).

Pure domain functions over a SQLAlchemy session. The API gateway exposes these;
keeping the logic here lets the orchestrator reuse it for background planning.

`today_context` produces the single calm morning summary (Now / Next / Later +
counts). `build_or_get_draft` turns the day's tasks into a DRAFT plan, and
`transition_plan` drives the plan through its lifecycle, emitting Today Context
events on every change.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AgentRun,
    Approval,
    DayPlan,
    Event,
    PlanBlock,
    Project,
    Task,
)

from .plan_state import PlanAction, PlanState, next_state

_NOW_STATUSES = ("active", "running")
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Canonical Today Context event types (kept in sync with the gateway event
# stream contract and packages/shared-types DayPilotEventType).
EVENT_PLAN_UPDATED = "plan.updated"
EVENT_BLOCK_STARTED = "block.started"


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _count(session: Session, stmt) -> int:
    return int(session.execute(stmt).scalar() or 0)


def _serialize_task(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "owner": t.owner,
        "executor": t.executor,
        "priority": t.priority,
        "status": t.status,
        "start": t.start_time,
        "end": t.end_time,
        "context": t.context,
        "projectId": t.project_id,
        "nextAction": t.next_action,
    }


def today_context(session: Session, workspace_id: str = "default") -> dict[str, Any]:
    running_agents = _count(
        session,
        select(func.count()).select_from(AgentRun).where(
            AgentRun.workspace_id == workspace_id, AgentRun.state == "running"
        ),
    )
    pending_approvals = _count(
        session,
        select(func.count()).select_from(Approval).where(
            Approval.workspace_id == workspace_id, Approval.status == "pending"
        ),
    )
    blocked_tasks = _count(
        session,
        select(func.count()).select_from(Task).where(
            Task.workspace_id == workspace_id, Task.status == "blocked"
        ),
    )
    active_projects = _count(
        session,
        select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id),
    )
    attention_projects = _count(
        session,
        select(func.count()).select_from(Project).where(
            Project.workspace_id == workspace_id, Project.risk != "low"
        ),
    )

    active_tasks = list(
        session.execute(
            select(Task)
            .where(Task.workspace_id == workspace_id, Task.status.in_(_NOW_STATUSES))
            .order_by(Task.start_time.asc().nulls_last(), Task.created_at.asc())
            .limit(6)
        ).scalars()
    )
    return {
        "workspaceId": workspace_id,
        "now": _serialize_task(active_tasks[0]) if active_tasks else None,
        "next": _serialize_task(active_tasks[1]) if len(active_tasks) > 1 else None,
        "later": [_serialize_task(t) for t in active_tasks[2:]],
        "counts": {
            "aiRunning": running_agents,
            "approvals": pending_approvals,
            "blockers": blocked_tasks,
            "projectsActive": active_projects,
            "projectsNeedAttention": attention_projects,
        },
    }


def _weekday_name(plan_date: str) -> str | None:
    try:
        parsed = date.fromisoformat(plan_date)
    except ValueError:
        return None
    return _WEEKDAYS[parsed.weekday()]


def get_plan(session: Session, workspace_id: str, plan_date: str) -> DayPlan | None:
    return session.execute(
        select(DayPlan).where(
            DayPlan.workspace_id == workspace_id, DayPlan.plan_date == plan_date
        )
    ).scalar_one_or_none()


def build_or_get_draft(session: Session, workspace_id: str, plan_date: str) -> DayPlan:
    """Return the plan for a date, creating a DRAFT from the day's tasks if none exists."""
    existing = get_plan(session, workspace_id, plan_date)
    if existing is not None:
        return existing

    plan = DayPlan(
        workspace_id=workspace_id,
        plan_date=plan_date,
        state=PlanState.DRAFT.value,
        summary="AI-drafted plan from today's tasks. Review and approve.",
    )
    session.add(plan)
    session.flush()

    weekday = _weekday_name(plan_date)
    task_stmt = select(Task).where(
        Task.workspace_id == workspace_id,
        Task.status.in_(("active", "running", "scheduled", "needs_approval")),
    )
    if weekday:
        task_stmt = task_stmt.where((Task.day == weekday) | (Task.day.is_(None)))
    tasks = list(
        session.execute(task_stmt.order_by(Task.start_time.asc().nulls_last()).limit(12)).scalars()
    )
    for order_index, task in enumerate(tasks):
        session.add(
            PlanBlock(
                day_plan_id=plan.id,
                task_id=task.id,
                title=task.title,
                start_time=task.start_time,
                end_time=task.end_time,
                owner=task.owner,
                source=task.executor or task.source or "",
                status=task.status,
                order_index=order_index,
            )
        )
    _emit(session, workspace_id, EVENT_PLAN_UPDATED, {"planDate": plan_date, "state": plan.state, "blocks": len(tasks)})
    session.flush()
    return plan


def transition_plan(
    session: Session, workspace_id: str, plan_date: str, action: PlanAction | str, summary: str | None = None
) -> DayPlan:
    """Apply a lifecycle action to the plan, emitting a plan.updated event."""
    plan = build_or_get_draft(session, workspace_id, plan_date)
    plan.state = next_state(plan.state, action).value
    if summary is not None:
        plan.summary = summary
    plan.updated_at = datetime.utcnow()
    _emit(session, workspace_id, EVENT_PLAN_UPDATED, {"planDate": plan_date, "state": plan.state, "action": str(action)})
    session.flush()
    return plan


def start_focus(session: Session, workspace_id: str, task_id: str) -> dict[str, Any]:
    """Enter Focus Mode on a task: emit block.started and return the focus context."""
    task = session.get(Task, task_id)
    if task is None:
        raise KeyError(task_id)
    project = session.get(Project, task.project_id) if task.project_id else None
    _emit(session, workspace_id, EVENT_BLOCK_STARTED, {"taskId": task_id, "title": task.title})
    session.flush()
    return {
        "task": _serialize_task(task),
        "project": {"id": project.id, "name": project.name} if project else None,
        "allowedActions": ["done", "blocked", "hand_to_ai"],
        "context": task.context or "",
    }
