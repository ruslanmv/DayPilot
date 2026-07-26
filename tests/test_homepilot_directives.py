"""HomePilot directive validation + task mapping (Batch A7).

The security surface: ``x_directives`` is untrusted model output. These tests
lock in that DayPilot re-validates from scratch, that only internal bookkeeping
is auto-applied, that every outside-world action becomes a pending approval
(never executed, never auto-completed), and that an agent can only touch its own
tasks.
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
from daypilot_orchestrator.homepilot import task_mapper
from daypilot_orchestrator.homepilot.directives import validate_directives


def _ws() -> str:
    return "ws-dir-" + uuid.uuid4().hex[:8]


# --- validation (pure, no DB) ----------------------------------------------

def test_validation_drops_unknown_types_and_bad_capabilities():
    payload = {"items": [
        {"type": "task.create", "title": "Real work"},
        {"type": "delete.everything"},                                   # unknown
        {"type": "daypilot.action.propose", "capability": "launch.nukes", "summary": "no"},  # bad cap
        {"type": "daypilot.action.propose", "capability": "email.send", "summary": "ok"},     # good
    ]}
    v = validate_directives(payload)
    kinds = [d.type for d in v.directives]
    assert kinds == ["task.create", "daypilot.action.propose"]
    reasons = {r.reason for r in v.rejected}
    assert "type_not_allowed" in reasons and "capability_not_allowed" in reasons


def test_validation_caps_count_and_clips_lengths():
    items = [{"type": "task.create", "title": "x" * 999} for _ in range(30)]
    v = validate_directives({"items": items})
    assert len(v.directives) == 12  # MAX_DIRECTIVES_PER_TURN
    assert all(len(d.title) <= 200 for d in v.directives)
    assert any(r.reason == "over_limit" for r in v.rejected)


def test_validation_normalizes_priority_and_percent():
    v = validate_directives({"items": [
        {"type": "task.create", "title": "t", "priority": "URGENT", "percent": 250},
        {"type": "progress.report", "ref": "h1", "percent": -5},
    ]})
    create = v.directives[0]
    assert create.priority == "medium"   # invalid priority → default
    assert create.percent == 100         # clamped
    assert v.directives[1].percent == 0  # clamped


def test_task_ref_directive_without_ref_is_rejected():
    v = validate_directives({"items": [{"type": "task.complete"}]})
    assert v.directives == []
    assert v.rejected[0].reason == "missing_task_ref"


# --- mapping (DB) -----------------------------------------------------------

def _link(session, ws: str, name: str = "Scarlett") -> HomePilotAgentLink:
    link = HomePilotAgentLink(workspace_id=ws, connection_id="c1", homepilot_project_id="p-" + name,
                              name=name, enabled=True, status="available")
    session.add(link)
    session.flush()
    return link


def test_task_create_makes_agent_owned_active_task():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        link = _link(s, ws)
        v = validate_directives({"items": [{"type": "task.create", "title": "Draft Q3 report", "ref": "h1"}]})
        res = task_mapper.apply_directives(s, ws, link, v)
        assert len(res.created) == 1
        t = s.get(Task, res.created[0])
        assert t.owner == "agent" and t.status == "active" and t.status != "completed"
        assert t.assigned_agent_link_id == link.id and t.created_by_agent_link_id == link.id
        assert (t.remote_reference or {}).get("ref") == "h1"


def test_action_propose_creates_waiting_task_and_pending_approval():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        link = _link(s, ws)
        v = validate_directives({"items": [{
            "type": "daypilot.action.propose", "capability": "email.send",
            "summary": "Send the client update", "arguments": {"to": "client@acme.com"},
        }]})
        res = task_mapper.apply_directives(s, ws, link, v)
        assert len(res.created) == 1 and len(res.approvals) == 1
        t = s.get(Task, res.created[0])
        assert t.status == "waiting_for_approval"          # a draft, never completed
        assert t.approval_id == res.approvals[0]
        assert t.remote_reference["capability"] == "email.send"
        appr = s.get(Approval, res.approvals[0])
        assert appr.status == "pending" and appr.resource_id == t.id and appr.action == "email.send"


def test_agent_cannot_complete_a_draft_or_touch_foreign_tasks():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        link = _link(s, ws)
        # 1) A proposal draft cannot be flipped to completed by a later directive.
        v1 = validate_directives({"items": [{
            "type": "daypilot.action.propose", "capability": "email.send", "summary": "x", "ref": "d1",
        }]})
        task_mapper.apply_directives(s, ws, link, v1)
        v2 = validate_directives({"items": [{"type": "task.complete", "ref": "d1"}]})
        res2 = task_mapper.apply_directives(s, ws, link, v2)
        assert res2.updated == []
        assert any(r["reason"] == "awaiting_approval" for r in res2.rejected)

        # 2) An agent can't complete a task it doesn't own (unknown handle).
        v3 = validate_directives({"items": [{"type": "task.complete", "ref": "not-mine"}]})
        res3 = task_mapper.apply_directives(s, ws, link, v3)
        assert res3.updated == []
        assert any(r["reason"] == "unknown_task_ref" for r in res3.rejected)


def test_mixed_agents_cannot_reach_each_others_tasks():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        a = _link(s, ws, "Scarlett")
        b = _link(s, ws, "Atlas")
        # Scarlett creates a task under handle h1.
        task_mapper.apply_directives(s, ws, a, validate_directives(
            {"items": [{"type": "task.create", "title": "Scarlett's task", "ref": "h1"}]}))
        # Atlas tries to update h1 — it isn't Atlas's, so it's unknown to Atlas.
        res = task_mapper.apply_directives(s, ws, b, validate_directives(
            {"items": [{"type": "task.update", "ref": "h1", "title": "hijacked"}]}))
        assert res.updated == []
        assert any(r["reason"] == "unknown_task_ref" for r in res.rejected)


def test_delegate_and_artifact_are_deferred_not_applied():
    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        link = _link(s, ws)
        v = validate_directives({"items": [
            {"type": "delegate.request", "title": "hand off"},
            {"type": "artifact.attach", "title": "a file"},
        ]})
        res = task_mapper.apply_directives(s, ws, link, v)
        assert res.created == [] and res.approvals == []
        assert set(res.deferred) == {"delegate.request", "artifact.attach"}
