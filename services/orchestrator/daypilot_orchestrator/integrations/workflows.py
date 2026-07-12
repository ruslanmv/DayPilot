"""Predefined cross-integration workflows (batch I8).

Simple, opt-in, predefined handlers — not a visual automation graph. Each takes a
normalized IntegrationEvent and produces a safe DayPilot artifact (a task or a
notification). Any *outbound* step (e.g. posting a reply) is not done here; it is
routed through the gateway/Slack write path so it stays approval-gated.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from daypilot_knowledge.db import AuditLog, Task

from .notifications import normalize, record_notification


def _audit(session: Session, action: str, payload: dict[str, Any]) -> None:
    session.add(AuditLog(event_type=f"workflow.{action}", risk="low", decision="recorded", payload_json=payload))


def slack_message_to_task(session: Session, event: dict[str, Any]) -> dict[str, Any]:
    """Slack message → create a DayPilot task."""
    ws = event.get("workspaceId", "default")
    task = Task(
        workspace_id=ws, title=f"Follow up: {event.get('summary', 'Slack message')[:160]}",
        owner="you", priority="medium", status="active", source="slack",
        context=event.get("summary", ""),
    )
    session.add(task)
    session.flush()
    _audit(session, "slack_message_to_task", {"taskId": task.id})
    return {"status": "ok", "taskId": task.id}


def github_failure_to_notify(session: Session, event: dict[str, Any]) -> dict[str, Any]:
    """GitHub build failure → surface an attention notification."""
    ws = event.get("workspaceId", "default")
    nid = record_notification(session, ws, normalize(
        "github", "connection.error", "GitHub build failed",
        event.get("summary", "A CI build failed on main."), severity="attention",
    ))
    _audit(session, "github_failure_to_notify", {"notificationId": nid})
    return {"status": "ok", "notificationId": nid}


def email_request_to_followup(session: Session, event: dict[str, Any]) -> dict[str, Any]:
    """Email request → create a project follow-up task."""
    ws = event.get("workspaceId", "default")
    task = Task(
        workspace_id=ws, title=f"Follow up (email): {event.get('summary', 'request')[:160]}",
        owner="you", priority="medium", status="active", source="email",
    )
    session.add(task)
    session.flush()
    _audit(session, "email_request_to_followup", {"taskId": task.id})
    return {"status": "ok", "taskId": task.id}


WORKFLOWS: dict[str, Callable[[Session, dict[str, Any]], dict[str, Any]]] = {
    "slack_message_to_task": slack_message_to_task,
    "github_failure_to_notify": github_failure_to_notify,
    "email_request_to_followup": email_request_to_followup,
}


def available_workflows() -> list[str]:
    return sorted(WORKFLOWS)


def run_workflow(
    session: Session,
    workflow_id: str,
    event: dict[str, Any],
    enabled: set[str] | None = None,
) -> dict[str, Any]:
    """Run a predefined workflow. If `enabled` is given, only those in the set run
    (workflows are opt-in)."""
    if enabled is not None and workflow_id not in enabled:
        return {"status": "disabled", "workflow": workflow_id}
    handler = WORKFLOWS.get(workflow_id)
    if handler is None:
        raise KeyError(workflow_id)
    return handler(session, event)
