"""Map validated persona directives to real DayPilot work (Batch A7).

Takes the safe :class:`Directive` list from :mod:`directives` and applies it to
the database. The security rules that make this safe:

  * An agent may only mutate tasks IT owns. Task-referencing directives resolve
    their target by the agent's own handle (``ref``) among tasks assigned to that
    agent link — never by a raw DayPilot task id, so one agent can't touch
    another's (or a human's) work.
  * Internal bookkeeping (create/update/complete/block/progress) is applied
    directly. Anything that would touch the outside world
    (``daypilot.action.propose``) becomes a task in ``waiting_for_approval`` plus
    a pending :class:`Approval` — it is NEVER executed here.
  * A directive-created task never starts (or is flipped to) ``completed`` while
    an approval is still pending: a draft is never "completed."
  * Delegation and artifact attachment are recognized but deferred to later
    phases; they are reported, not applied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, HomePilotAgentLink, Task
from daypilot_knowledge.db.models import utcnow

from . import delegation as hp_delegation
from .directives import Directive, ValidationResult

# External-write risk per capability, surfaced on the Approval.
_CAPABILITY_RISK: dict[str, str] = {
    "email.send": "medium",
    "message.send": "medium",
    "calendar.create": "low",
    "calendar.update": "low",
    "calendar.cancel": "medium",
    "document.generate": "low",
    "coding.run": "high",
    "github.change": "high",
    "finance.change": "high",
    "hr.change": "high",
    "system.change": "high",
}

# Directives recognized but not applied yet (delegation is handled in A9;
# artifact.attach remains deferred to a later phase).
_DEFERRED_TYPES = frozenset({"artifact.attach"})


@dataclass
class MapResult:
    created: list[str] = field(default_factory=list)      # new task ids
    updated: list[str] = field(default_factory=list)      # mutated task ids
    approvals: list[str] = field(default_factory=list)    # new approval ids
    delegations: list[dict[str, Any]] = field(default_factory=list)  # delegated sub-tasks
    deferred: list[str] = field(default_factory=list)     # directive types not applied yet
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "updated": list(self.updated),
            "approvals": list(self.approvals),
            "delegations": list(self.delegations),
            "deferred": list(self.deferred),
            "rejected": list(self.rejected),
            "counts": {
                "created": len(self.created),
                "updated": len(self.updated),
                "approvals": len(self.approvals),
                "delegations": len(self.delegations),
                "deferred": len(self.deferred),
                "rejected": len(self.rejected),
            },
        }


def _owned_tasks(session: Session, workspace_id: str, link_id: str) -> list[Task]:
    return list(
        session.execute(
            select(Task).where(
                Task.workspace_id == workspace_id,
                Task.assigned_agent_link_id == link_id,
            )
        ).scalars()
    )


def _find_by_ref(tasks: list[Task], ref: str | None) -> Task | None:
    if not ref:
        return None
    for t in tasks:
        if (t.remote_reference or {}).get("ref") == ref:
            return t
    return None


def _is_draft(task: Task) -> bool:
    """A task still gated by a pending approval — never completable."""
    return task.status == "waiting_for_approval" or bool(task.approval_id)


def apply_directives(
    session: Session,
    workspace_id: str,
    link: HomePilotAgentLink,
    validation: ValidationResult,
    *,
    source_label: str | None = None,
) -> MapResult:
    """Apply validated directives for one agent turn. Flushes but does not commit
    (the caller owns the transaction)."""
    result = MapResult()
    # Carry validation rejections through so the caller sees the whole picture.
    for r in validation.rejected:
        result.rejected.append({"index": r.index, "type": r.type, "reason": r.reason})

    source = source_label or f"homepilot:{link.name or link.id}"
    # Snapshot of this agent's tasks for ref resolution; new creates are appended
    # so a later directive in the same turn can reference an earlier create.
    owned = _owned_tasks(session, workspace_id, link.id)

    for d in validation.directives:
        if d.type == "delegate.request":
            _handle_delegation(session, workspace_id, link, d, owned, result)
            continue
        if d.type in _DEFERRED_TYPES:
            result.deferred.append(d.type)
            continue

        if d.type == "task.create":
            task = _create_task(session, workspace_id, link, d, source)
            owned.append(task)
            result.created.append(task.id)
            continue

        if d.type == "daypilot.action.propose":
            task, approval = _create_proposal(session, workspace_id, link, d, source)
            owned.append(task)
            result.created.append(task.id)
            result.approvals.append(approval.id)
            continue

        # Task-mutating directives — resolve the agent's OWN task by handle.
        target = _find_by_ref(owned, d.ref)
        if target is None:
            result.rejected.append({"type": d.type, "reason": "unknown_task_ref", "ref": d.ref})
            continue
        applied = _mutate_task(target, d, result)
        if applied:
            result.updated.append(target.id)

    session.flush()
    return result


def _handle_delegation(
    session: Session,
    workspace_id: str,
    link: HomePilotAgentLink,
    d: Directive,
    owned: list[Task],
    result: MapResult,
) -> None:
    """Delegate a sub-task to a worker agent when the DELEGATION feature is on.
    Off → deferred. All safety limits live in the delegation engine."""
    if not hp_delegation.enabled():
        result.deferred.append("delegate.request")
        return
    parent = _find_by_ref(owned, d.ref)
    res = hp_delegation.delegate(
        session, workspace_id, link,
        title=d.title, capability=d.capability or "", detail=d.detail, parent_task=parent,
    )
    if res.code == "delegated":
        result.delegations.append(res.as_dict())
        # The child belongs to the WORKER, not the manager — deliberately not
        # added to the manager's `owned` set (no cross-agent task ownership).
        if res.child_task_id:
            result.created.append(res.child_task_id)
    else:
        result.rejected.append({"type": "delegate.request", "reason": res.reason})


def _create_task(session: Session, workspace_id: str, link: HomePilotAgentLink, d: Directive, source: str) -> Task:
    task = Task(
        workspace_id=workspace_id,
        title=d.title,
        owner="agent",
        executor=link.name or "",
        priority=d.priority,
        status="active",  # the agent is now tracking this work — never "completed"
        context=d.detail or None,
        source=source,
        assigned_agent_link_id=link.id,
        created_by_agent_link_id=link.id,
        progress_percent=d.percent or 0,
        remote_reference={"ref": d.ref} if d.ref else {},
    )
    session.add(task)
    session.flush()
    return task


def _create_proposal(
    session: Session, workspace_id: str, link: HomePilotAgentLink, d: Directive, source: str
) -> tuple[Task, Approval]:
    """An external-world proposal: a waiting task + a pending approval. Nothing is
    executed — approving it in the Approval Center is a later, explicit step."""
    task = Task(
        workspace_id=workspace_id,
        title=d.title or (d.capability or "Proposed action"),
        owner="agent",
        executor=link.name or "",
        priority=d.priority,
        status="waiting_for_approval",  # a draft — never shown as completed
        context=d.detail or None,
        source=source,
        risk=_CAPABILITY_RISK.get(d.capability or "", "medium"),
        assigned_agent_link_id=link.id,
        created_by_agent_link_id=link.id,
        progress_percent=0,
        remote_reference={
            "kind": "action.propose",
            "capability": d.capability,
            "arguments": d.arguments,
            "lifecycle": "awaiting",  # a draft awaiting approval (A8 lifecycle)
            **({"ref": d.ref} if d.ref else {}),
        },
    )
    session.add(task)
    session.flush()

    approval = Approval(
        workspace_id=workspace_id,
        action=d.capability or "action",
        summary=d.title or (d.capability or ""),
        risk=_CAPABILITY_RISK.get(d.capability or "", "medium"),
        status="pending",
        resource_type="task",
        resource_id=task.id,
        reason=f"Proposed by {link.name or 'agent'} via HomePilot",
    )
    session.add(approval)
    session.flush()

    task.approval_id = approval.id
    session.flush()
    return task, approval


def _mutate_task(target: Task, d: Directive, result: MapResult) -> bool:
    now = utcnow()
    if d.type == "task.complete":
        if _is_draft(target):
            # A draft (pending approval) can never be completed by a model turn.
            result.rejected.append({"type": d.type, "reason": "awaiting_approval", "ref": d.ref})
            return False
        target.status = "completed"
        target.progress_percent = 100
        target.updated_at = now
        return True

    if d.type == "task.block":
        target.status = "blocked"
        if d.detail:
            target.context = d.detail
        target.updated_at = now
        return True

    if d.type == "task.update":
        if d.title:
            target.title = d.title
        if d.detail:
            target.context = d.detail
        if d.priority:
            target.priority = d.priority
        if d.percent is not None:
            target.progress_percent = d.percent
        target.updated_at = now
        return True

    if d.type == "progress.report":
        if d.percent is not None:
            target.progress_percent = d.percent
        if d.detail:
            target.next_action = d.detail
        target.updated_at = now
        return True

    return False
