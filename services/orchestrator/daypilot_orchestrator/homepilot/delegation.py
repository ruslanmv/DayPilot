"""Delegation between HomePilot agents (Batch A9).

A manager persona can hand a sub-task to a worker persona. HomePilot runs the
personas; DayPilot records and *governs* the delegation, enforcing hard safety
limits before any child task or delegation row is written:

  * no self-delegation and no cycles (a worker can't be its manager's ancestor);
  * depth ≤ ``MAX_DELEGATION_DEPTH`` (2) — You → manager → worker, no deeper;
  * ≤ ``MAX_WORKER_AGENTS`` (3) workers per manager task;
  * ≤ ``MAX_CHILD_TASKS`` (10) child tasks under one parent;
  * a worker is never granted a capability the manager doesn't itself have
    (worker permissions ≤ manager);
  * both agents belong to the SAME account (multi-account security).

Everything a worker proposes still flows through DayPilot's Approval Center
(A7/A8) — delegation never bypasses approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import AgentDelegation, HomePilotAgentLink, Task

from . import capability_matcher as matcher
from .contracts import (
    MAX_CHILD_TASKS,
    MAX_DELEGATION_DEPTH,
    MAX_WORKER_AGENTS,
    feature_enabled,
    HomePilotFeature,
)


def enabled() -> bool:
    return feature_enabled(HomePilotFeature.DELEGATION)


@dataclass
class DelegationResult:
    code: str                       # delegated | rejected
    reason: str = ""
    worker_link_id: str | None = None
    worker_name: str | None = None
    child_task_id: str | None = None
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            "workerLinkId": self.worker_link_id,
            "workerName": self.worker_name,
            "childTaskId": self.child_task_id,
            "depth": self.depth,
        }


def _rej(reason: str) -> DelegationResult:
    return DelegationResult(code="rejected", reason=reason)


def _manager_ancestors(session: Session, workspace_id: str, link_id: str) -> set[str]:
    """All agents that (directly or transitively) delegated down to ``link_id``.
    Used for cycle detection — a worker must not be one of these."""
    ancestors: set[str] = set()
    frontier = [link_id]
    while frontier:
        current = frontier.pop()
        rows = session.execute(
            select(AgentDelegation.manager_agent_link_id).where(
                AgentDelegation.workspace_id == workspace_id,
                AgentDelegation.worker_agent_link_id == current,
            )
        ).scalars()
        for mgr in rows:
            if mgr and mgr not in ancestors:
                ancestors.add(mgr)
                frontier.append(mgr)
    return ancestors


def _eligible_workers(
    session: Session, workspace_id: str, manager: HomePilotAgentLink, exclude: set[str]
) -> list[HomePilotAgentLink]:
    rows = session.execute(
        select(HomePilotAgentLink).where(
            HomePilotAgentLink.workspace_id == workspace_id,
            HomePilotAgentLink.enabled.is_(True),
        )
    ).scalars()
    out = []
    for link in rows:
        if link.id in exclude or link.id == manager.id:
            continue
        # Same account only (multi-account security).
        if manager.account_ref and link.account_ref and link.account_ref != manager.account_ref:
            continue
        if link.status == "offline":
            continue
        out.append(link)
    return out


def _manager_depth(session: Session, workspace_id: str, link_id: str) -> int:
    """The manager's own depth in the chain (1 for a top-level manager the user
    talks to; 2 if it was itself delegated to)."""
    depths = session.execute(
        select(AgentDelegation.depth).where(
            AgentDelegation.workspace_id == workspace_id,
            AgentDelegation.worker_agent_link_id == link_id,
        )
    ).scalars().all()
    return max(depths) if depths else 1


def delegate(
    session: Session,
    workspace_id: str,
    manager: HomePilotAgentLink,
    *,
    title: str,
    capability: str = "",
    detail: str = "",
    parent_task: Task | None = None,
) -> DelegationResult:
    """Delegate one sub-task from ``manager`` to the best-matched worker, subject
    to the safety limits. Flushes but does not commit."""
    manager_depth = _manager_depth(session, workspace_id, manager.id)
    worker_depth = manager_depth + 1
    if worker_depth > MAX_DELEGATION_DEPTH:
        return _rej("max_depth")

    # Worker permissions ≤ manager: the manager can't delegate a capability it
    # doesn't itself hold.
    manager_caps = {str(c).strip().lower() for c in (manager.capabilities_json or [])}
    if capability and manager_caps and capability.strip().lower() not in manager_caps:
        return _rej("exceeds_manager")

    parent_id = parent_task.id if parent_task is not None else None

    # ≤ MAX_WORKER_AGENTS distinct workers for this manager + parent task.
    existing = session.execute(
        select(AgentDelegation).where(
            AgentDelegation.workspace_id == workspace_id,
            AgentDelegation.manager_agent_link_id == manager.id,
            AgentDelegation.parent_task_id == parent_id,
        )
    ).scalars().all()
    if len({d.worker_agent_link_id for d in existing}) >= MAX_WORKER_AGENTS:
        return _rej("max_workers")

    # ≤ MAX_CHILD_TASKS child tasks under the parent.
    if parent_id is not None:
        child_count = session.execute(
            select(Task).where(Task.workspace_id == workspace_id, Task.parent_task_id == parent_id)
        ).scalars().all()
        if len(child_count) >= MAX_CHILD_TASKS:
            return _rej("max_child_tasks")

    ancestors = _manager_ancestors(session, workspace_id, manager.id)
    ancestors.add(manager.id)  # also excludes self
    candidates = _eligible_workers(session, workspace_id, manager, exclude=ancestors)
    worker = matcher.match_worker([matcher.to_candidate(c) for c in candidates], capability)
    if worker is None:
        return _rej("no_worker")
    worker_link = next(c for c in candidates if c.id == worker.link_id)

    child = Task(
        workspace_id=workspace_id,
        title=title or f"Delegated: {capability or 'sub-task'}",
        owner="agent",
        executor=worker_link.name or "",
        priority=(parent_task.priority if parent_task is not None else "medium"),
        status="active",
        context=detail or None,
        source=f"homepilot:{manager.name or manager.id}",
        assigned_agent_link_id=worker_link.id,
        manager_agent_link_id=manager.id,
        created_by_agent_link_id=manager.id,
        parent_task_id=parent_id,
        progress_percent=0,
        remote_reference={"kind": "delegated", "capability": capability},
    )
    session.add(child)
    session.flush()

    session.add(AgentDelegation(
        workspace_id=workspace_id,
        manager_agent_link_id=manager.id,
        worker_agent_link_id=worker_link.id,
        parent_task_id=parent_id,
        child_task_id=child.id,
        capability=capability,
        depth=worker_depth,
        status="assigned",
        reason=detail or None,
    ))
    session.flush()

    return DelegationResult(
        code="delegated",
        worker_link_id=worker_link.id,
        worker_name=worker_link.name,
        child_task_id=child.id,
        depth=worker_depth,
    )


def _name(session: Session, workspace_id: str, link_id: str | None) -> str:
    if not link_id:
        return ""
    link = session.get(HomePilotAgentLink, link_id)
    return link.name if link is not None else ""


def responsibility_chain(session: Session, workspace_id: str, link_id: str) -> list[str]:
    """The chain of responsibility ending at ``link_id`` (e.g. ``["You",
    "Scarlett", "Atlas"]``). Walks the delegation graph upward from the agent."""
    chain = [_name(session, workspace_id, link_id) or "Agent"]
    seen = {link_id}
    current = link_id
    while True:
        mgr = session.execute(
            select(AgentDelegation.manager_agent_link_id).where(
                AgentDelegation.workspace_id == workspace_id,
                AgentDelegation.worker_agent_link_id == current,
            ).order_by(AgentDelegation.created_at.asc())
        ).scalars().first()
        if not mgr or mgr in seen:
            break
        seen.add(mgr)
        chain.insert(0, _name(session, workspace_id, mgr) or "Agent")
        current = mgr
    return ["You", *chain]


def list_delegations(session: Session, workspace_id: str, link_id: str) -> dict[str, Any]:
    """Delegations where this agent is manager or worker, newest first, with the
    responsibility chain for each."""
    rows = session.execute(
        select(AgentDelegation).where(
            AgentDelegation.workspace_id == workspace_id,
            (AgentDelegation.manager_agent_link_id == link_id)
            | (AgentDelegation.worker_agent_link_id == link_id),
        ).order_by(AgentDelegation.created_at.desc())
    ).scalars()
    out = []
    for d in rows:
        out.append({
            "id": d.id,
            "manager": _name(session, workspace_id, d.manager_agent_link_id),
            "managerLinkId": d.manager_agent_link_id,
            "worker": _name(session, workspace_id, d.worker_agent_link_id),
            "workerLinkId": d.worker_agent_link_id,
            "capability": d.capability,
            "depth": d.depth,
            "status": d.status,
            "childTaskId": d.child_task_id,
            "chain": responsibility_chain(session, workspace_id, d.worker_agent_link_id),
            "createdAt": d.created_at.isoformat() if d.created_at else None,
        })
    return {"agentId": link_id, "delegations": out}
