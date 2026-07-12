"""End-of-day wrap-up generation (batch B4).

Summarizes what happened today — progress, unresolved risks, and AI-generated
outputs — and drafts tomorrow's plan so the next morning opens with continuity
rather than a blank page. Deterministic today; batch B5 lets Ollabridge phrase
the narrative summary.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import CodingRun, Project, Task

from .plan_state import PlanState
from .today_engine import EVENT_PLAN_UPDATED, build_or_get_draft, get_plan


def _count(session: Session, stmt) -> int:
    return int(session.execute(stmt).scalar() or 0)


def generate_wrapup(session: Session, workspace_id: str, plan_date: str) -> dict[str, Any]:
    """Produce the end-of-day summary and persist tomorrow's DRAFT plan."""
    total_tasks = _count(
        session,
        select(func.count()).select_from(Task).where(Task.workspace_id == workspace_id),
    )
    done_tasks = _count(
        session,
        select(func.count()).select_from(Task).where(
            Task.workspace_id == workspace_id, Task.status == "done"
        ),
    )
    blocked = list(
        session.execute(
            select(Task).where(
                Task.workspace_id == workspace_id, Task.status == "blocked"
            ).limit(10)
        ).scalars()
    )
    risky_projects = list(
        session.execute(
            select(Project).where(
                Project.workspace_id == workspace_id, Project.risk != "low"
            ).limit(10)
        ).scalars()
    )
    generated = list(
        session.execute(
            select(CodingRun).where(
                CodingRun.workspace_id == workspace_id,
                CodingRun.status.in_(("needs_review", "approved", "merged")),
            ).limit(10)
        ).scalars()
    )

    # Draft tomorrow so the next morning continues rather than restarts.
    tomorrow = (date.fromisoformat(plan_date) + timedelta(days=1)).isoformat() if _is_date(plan_date) else None
    tomorrow_plan = None
    if tomorrow:
        plan = build_or_get_draft(session, workspace_id, tomorrow)
        tomorrow_plan = {"planDate": tomorrow, "state": plan.state}

    # Mark today's plan wrapped if it exists and is active.
    today_plan = get_plan(session, workspace_id, plan_date)
    if today_plan is not None and today_plan.state == PlanState.ACTIVE.value:
        today_plan.state = PlanState.WRAPPED.value
        session.add(_wrap_event(workspace_id, plan_date))

    completion = round(done_tasks / total_tasks, 3) if total_tasks else 0.0
    return {
        "workspaceId": workspace_id,
        "planDate": plan_date,
        "progress": {
            "tasksDone": done_tasks,
            "tasksTotal": total_tasks,
            "completionRate": completion,
        },
        "unresolvedRisks": [
            {"kind": "blocked_task", "id": t.id, "title": t.title} for t in blocked
        ]
        + [
            {"kind": "project_risk", "id": p.id, "title": p.name, "risk": p.risk}
            for p in risky_projects
        ],
        "generatedOutputs": [
            {"id": c.id, "repo": c.repo, "branch": c.branch, "status": c.status}
            for c in generated
        ],
        "tomorrow": tomorrow_plan,
    }


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _wrap_event(workspace_id: str, plan_date: str):
    from daypilot_knowledge.db import Event

    return Event(
        workspace_id=workspace_id,
        type=EVENT_PLAN_UPDATED,
        payload_json={"planDate": plan_date, "state": PlanState.WRAPPED.value, "action": "wrap"},
    )
