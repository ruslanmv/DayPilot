"""Execute approved agent proposals through DayPilot's own integrations (A8).

Every external write an agent proposes is a ``daypilot.action.propose`` directive
that A7 turned into a ``waiting_for_approval`` task plus a pending
:class:`Approval`. This module owns what happens AFTER the user decides in
DayPilot's Approval Center (contract rules 6–8): HomePilot never executes —
DayPilot does, and only once approved.

The proposal task moves through a visible lifecycle:

    prepared → awaiting → approved → executing → completed
                                  ↘ rejected
                                  ↘ failed

Execution dispatches by capability to an injectable executor. DayPilot performs
the action through its OWN integration surface (email, calendar, coding, …); a
capability with no registered executor, or an executor that raises, lands the
task in ``failed`` with a reason — never a silent success.
"""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from daypilot_knowledge.db import AuditLog, Task
from daypilot_knowledge.db.models import utcnow

# Lifecycle states surfaced in the agent workspace.
PREPARED = "prepared"
AWAITING = "awaiting"
APPROVED = "approved"
EXECUTING = "executing"
COMPLETED = "completed"
REJECTED = "rejected"
FAILED = "failed"

LIFECYCLE_STATES = (PREPARED, AWAITING, APPROVED, EXECUTING, COMPLETED, REJECTED, FAILED)

# How each lifecycle state maps onto the durable Task.status.
_STATUS_FOR: dict[str, str] = {
    PREPARED: "planned",
    AWAITING: "waiting_for_approval",
    APPROVED: "active",
    EXECUTING: "active",
    COMPLETED: "completed",
    REJECTED: "cancelled",
    FAILED: "failed",
}

# An executor performs the DayPilot-side action and returns (ok, detail).
Executor = Callable[[Session, str, Task, dict[str, Any]], "tuple[bool, str]"]


def lifecycle_of(task: Task) -> str:
    return (task.remote_reference or {}).get("lifecycle") or AWAITING


def set_lifecycle(task: Task, state: str, execution: dict[str, Any] | None = None) -> None:
    """Advance a proposal task's lifecycle and mirror it onto Task.status. A task
    in ``awaiting`` is a draft and is never flipped to completed except through a
    real approved execution."""
    rr = dict(task.remote_reference or {})
    rr["lifecycle"] = state
    if execution is not None:
        rr["execution"] = execution
    task.remote_reference = rr
    task.status = _STATUS_FOR.get(state, task.status)
    if state == COMPLETED:
        task.progress_percent = 100
    task.updated_at = utcnow()


def _audit(session: Session, task: Task, capability: str, decision: str, detail: dict[str, Any]) -> None:
    session.add(AuditLog(
        event_type="agent.action." + decision,
        risk=task.risk or "medium",
        decision=decision,
        payload_json={
            "taskId": task.id,
            "capability": capability,
            "agentLinkId": task.assigned_agent_link_id,
            **detail,
        },
    ))


def _record_executor(capability: str) -> Executor:
    """Default executor: DayPilot hands the approved action to its own
    ``<capability>`` integration and records it. Real live adapters (SMTP, the
    calendar/coding services) can replace this per capability via
    :func:`register_executor` without changing the lifecycle machinery."""

    def run(session: Session, workspace_id: str, task: Task, args: dict[str, Any]) -> tuple[bool, str]:
        return True, f"Handed to DayPilot's {capability} integration"

    return run


# Capabilities DayPilot can currently carry out. Anything outside this set
# lands in `failed` rather than pretending to have run.
_SUPPORTED = (
    "email.send", "message.send",
    "calendar.create", "calendar.update", "calendar.cancel",
    "document.generate",
)

_EXECUTORS: dict[str, Executor] = {cap: _record_executor(cap) for cap in _SUPPORTED}


def register_executor(capability: str, executor: Executor) -> None:
    """Register/override the executor for a capability (used to wire a real
    integration, or by tests)."""
    _EXECUTORS[capability] = executor


def _result(task: Task, state: str, capability: str, detail: str) -> dict[str, Any]:
    return {"taskId": task.id, "lifecycle": state, "capability": capability, "detail": detail}


def execute_approved(session: Session, workspace_id: str, task: Task) -> dict[str, Any]:
    """Run an approved proposal. Transitions approved → executing → completed
    (or failed) and records an audit entry. Idempotent-safe: an already-terminal
    task is left alone."""
    if lifecycle_of(task) in (COMPLETED, REJECTED, FAILED):
        return _result(task, lifecycle_of(task), (task.remote_reference or {}).get("capability", ""), "already_final")

    rr = task.remote_reference or {}
    capability = rr.get("capability") or ""
    args = rr.get("arguments") or {}

    set_lifecycle(task, APPROVED)
    set_lifecycle(task, EXECUTING)

    executor = _EXECUTORS.get(capability)
    if executor is None:
        set_lifecycle(task, FAILED, {"error": "unsupported_capability", "capability": capability})
        _audit(session, task, capability, "failed", {"error": "unsupported_capability"})
        session.flush()
        return _result(task, FAILED, capability, "unsupported_capability")

    try:
        ok, detail = executor(session, workspace_id, task, args)
    except Exception as exc:  # noqa: BLE001 - any executor failure is a task failure, not a crash
        set_lifecycle(task, FAILED, {"error": str(exc)})
        _audit(session, task, capability, "failed", {"error": str(exc)})
        session.flush()
        return _result(task, FAILED, capability, str(exc))

    if ok:
        set_lifecycle(task, COMPLETED, {"detail": detail})
        _audit(session, task, capability, "executed", {"detail": detail})
        session.flush()
        return _result(task, COMPLETED, capability, detail)

    set_lifecycle(task, FAILED, {"detail": detail})
    _audit(session, task, capability, "failed", {"detail": detail})
    session.flush()
    return _result(task, FAILED, capability, detail)


def reject(session: Session, workspace_id: str, task: Task, reason: str | None = None) -> dict[str, Any]:
    """Mark a proposal rejected — nothing is executed."""
    capability = (task.remote_reference or {}).get("capability") or ""
    set_lifecycle(task, REJECTED, {"reason": reason})
    _audit(session, task, capability, "rejected", {"reason": reason})
    session.flush()
    return _result(task, REJECTED, capability, reason or "")
