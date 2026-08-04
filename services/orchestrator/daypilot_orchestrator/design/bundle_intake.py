"""Design Bundle intake and design-review routing (batch B8).

Turns a Matrix Designer bundle into scheduled DayPilot work: each ordered batch
becomes a task the coding executors (GitPilot by default) can build, preserving
dependency order. Design reviews land on the project and the Command feed as
needs-attention signals.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event, Project, Task

from .matrix_designer_adapter import DesignBundle, DesignReview

EVENT_PLAN_UPDATED = "plan.updated"
EVENT_BLOCKER_RAISED = "blocker.raised"


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def intake_bundle(
    session: Session,
    workspace_id: str,
    bundle: DesignBundle,
    project_id: str | None = None,
    repository: str = "",
) -> dict[str, Any]:
    """Create a project (if needed) and one scheduled task per batch, in order.

    ``repository`` is where the batches will be built. Recorded on the project so
    every coding run inherits it; an existing project keeps the repo it has
    unless one is supplied.
    """
    project = session.get(Project, project_id) if project_id else None
    if project is None:
        project = Project(
            workspace_id=workspace_id,
            name=bundle.title,
            repository=repository.strip(),
            status="Active",
            risk="low",
            ai_activity="Design bundle intake",
            next_human_action=(
                "Review the batch roadmap and approve the first batch."
                if repository.strip()
                else "Add the repository to build in, then approve the first batch."
            ),
            recent_signals=[f"Matrix Designer bundle: {len(bundle.batches)} batches"],
        )
        session.add(project)
        session.flush()
    elif repository.strip():
        project.repository = repository.strip()

    created_tasks: list[str] = []
    for order, batch in enumerate(bundle.batches):
        # Batches with unmet dependencies are blocked; the first is active.
        status = "blocked" if batch.depends_on else ("active" if order == 0 else "scheduled")
        task = Task(
            workspace_id=workspace_id,
            title=f"[{batch.id}] {batch.title}",
            owner="ai",
            executor="GitPilot",
            priority="high" if order == 0 else "medium",
            status=status,
            source="design_bundle",
            project_id=project.id,
            context=batch.description,
            next_action="; ".join(batch.acceptance[:2]) if batch.acceptance else "Build this batch.",
        )
        session.add(task)
        session.flush()
        created_tasks.append(task.id)

    _emit(
        session, workspace_id, EVENT_PLAN_UPDATED,
        {"source": "design_bundle", "projectId": project.id, "batches": len(bundle.batches)},
    )
    session.flush()
    return {
        "projectId": project.id,
        "projectName": project.name,
        "repository": project.repository or "",
        "taskIds": created_tasks,
        "batches": len(bundle.batches),
    }


def apply_review(
    session: Session, workspace_id: str, review: DesignReview, project_id: str | None = None
) -> dict[str, Any]:
    """Attach a design review to a project as recent signals / attention state."""
    project = session.get(Project, project_id) if project_id else None
    major = [f for f in review.findings if f.severity in {"major", "critical"}]
    if project is not None:
        signal = f"Design review {review.grade} ({review.score}/100): {len(review.findings)} findings"
        project.recent_signals = [signal, *(project.recent_signals or [])][:8]
        project.designer_input = [f.note for f in review.findings][:8]
        if major:
            project.risk = "high" if any(f.severity == "critical" for f in major) else "medium"

    if major:
        _emit(
            session, workspace_id, EVENT_BLOCKER_RAISED,
            {"source": "design_review", "target": review.target, "majorFindings": len(major)},
        )
    session.flush()
    return {
        "reviewId": review.review_id,
        "target": review.target,
        "score": review.score,
        "grade": review.grade,
        "findings": [
            {"severity": f.severity, "area": f.area, "note": f.note} for f in review.findings
        ],
        "suggestions": review.suggestions,
        "projectId": project.id if project else None,
    }
