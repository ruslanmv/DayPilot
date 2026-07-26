"""HomePilot approval action mapping — execute-on-approve lifecycle (Batch A8).

Every external write an agent proposes flows through DayPilot's Approval Center.
These tests lock in the lifecycle: a proposal is awaiting → (approve) executing →
completed via DayPilot's own integration, (reject) rejected, and (unsupported /
erroring executor) failed — HomePilot never executes anything itself.
"""
from __future__ import annotations

import uuid

from daypilot_knowledge.db import (
    Approval,
    HomePilotAgentLink,
    Task,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.homepilot import action_mapping, task_mapper
from daypilot_orchestrator.homepilot.directives import validate_directives


def _ws() -> str:
    return "ws-act-" + uuid.uuid4().hex[:8]


def _link(session, ws: str, name: str = "Scarlett") -> HomePilotAgentLink:
    link = HomePilotAgentLink(workspace_id=ws, connection_id="c1", homepilot_project_id="p-" + name,
                              name=name, enabled=True, status="available")
    session.add(link)
    session.flush()
    return link


def _propose(session, ws, link, capability="email.send"):
    v = validate_directives({"items": [{
        "type": "daypilot.action.propose", "capability": capability, "summary": "Do the thing",
    }]})
    res = task_mapper.apply_directives(session, ws, link, v)
    task = session.get(Task, res.created[0])
    approval = session.get(Approval, res.approvals[0])
    return task, approval


def test_proposal_starts_awaiting():
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        task, approval = _propose(s, ws, _link(s, ws))
        assert action_mapping.lifecycle_of(task) == "awaiting"
        assert task.status == "waiting_for_approval" and approval.status == "pending"


def test_approve_executes_and_completes():
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        task, approval = _propose(s, ws, _link(s, ws), capability="email.send")
        approval.status = "approved"  # the Approval Center decided
        out = action_mapping.execute_approved(s, ws, task)
        assert out["lifecycle"] == "completed"
        assert task.status == "completed" and task.progress_percent == 100
        assert (task.remote_reference or {})["lifecycle"] == "completed"


def test_reject_marks_rejected_and_executes_nothing():
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        task, _ = _propose(s, ws, _link(s, ws))
        out = action_mapping.reject(s, ws, task, reason="not now")
        assert out["lifecycle"] == "rejected"
        assert task.status == "cancelled" and task.status != "completed"


def test_unsupported_capability_fails_not_silently_completes():
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        # github.change has no registered executor by default → failed.
        task, _ = _propose(s, ws, _link(s, ws), capability="github.change")
        out = action_mapping.execute_approved(s, ws, task)
        assert out["lifecycle"] == "failed"
        assert task.status == "failed" and task.status != "completed"


def test_executor_error_lands_in_failed():
    ws = _ws()

    def boom(session, workspace_id, task, args):
        raise RuntimeError("smtp down")

    action_mapping.register_executor("message.send", boom)
    try:
        with session_scope(create_engine_from_settings()) as s:
            task, _ = _propose(s, ws, _link(s, ws), capability="message.send")
            out = action_mapping.execute_approved(s, ws, task)
            assert out["lifecycle"] == "failed" and "smtp down" in out["detail"]
    finally:
        # Restore the default executor so other tests aren't affected.
        action_mapping.register_executor("message.send", action_mapping._record_executor("message.send"))


def test_on_approval_decided_ignores_non_agent_approvals():
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        # A plain approval with no agent task behind it — must be untouched.
        appr = Approval(workspace_id=ws, action="email.send", status="approved",
                        resource_type="email", resource_id="not-a-task")
        s.add(appr)
        s.flush()
        from app import homepilot_platform as hp
        assert hp.on_approval_decided(s, appr) is None
