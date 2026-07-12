"""Continue-from-yesterday memory (batch B4).

Restores per-project working state each morning — what happened yesterday, what
needs to happen today, what AI is doing, linked artifacts, blockers, and the
next recommended action — so the user resumes instead of re-orienting.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import CodingRun, Project, Task


def project_continuity(session: Session, workspace_id: str, project: Project) -> dict[str, Any]:
    open_tasks = list(
        session.execute(
            select(Task).where(
                Task.workspace_id == workspace_id,
                Task.project_id == project.id,
                Task.status.in_(("active", "running", "scheduled", "blocked", "needs_approval")),
            ).order_by(Task.updated_at.desc()).limit(8)
        ).scalars()
    )
    blockers = [t.title for t in open_tasks if t.status == "blocked"]
    coding = list(
        session.execute(
            select(CodingRun).where(
                CodingRun.workspace_id == workspace_id, CodingRun.project_id == project.id
            ).order_by(CodingRun.updated_at.desc()).limit(3)
        ).scalars()
    )
    next_action = (
        project.next_human_action
        or (open_tasks[0].next_action if open_tasks and open_tasks[0].next_action else None)
        or (open_tasks[0].title if open_tasks else "Review project status")
    )
    return {
        "projectId": project.id,
        "name": project.name,
        "risk": project.risk,
        "progress": project.progress,
        "yesterday": list(project.yesterday or []),
        "today": list(project.today or []),
        "aiActivity": project.ai_activity,
        "linkedSources": list(project.linked_sources or []),
        "branches": [c.branch for c in coding if c.branch],
        "blockers": blockers or list(project.blocked or []),
        "nextAction": next_action,
        "continueAction": project.continue_action or "Continue work",
    }


def continue_from_yesterday(
    session: Session, workspace_id: str = "default", limit: int = 20
) -> list[dict[str, Any]]:
    """Restore continuity records, most-at-risk projects first."""
    projects = list(
        session.execute(
            select(Project).where(Project.workspace_id == workspace_id).limit(limit)
        ).scalars()
    )
    # Surface risky projects first so attention lands where it is needed.
    risk_rank = {"high": 0, "medium": 1, "low": 2}
    projects.sort(key=lambda p: risk_rank.get(p.risk, 3))
    return [project_continuity(session, workspace_id, p) for p in projects]
