"""HomePilot agent delegation + safety limits (Batch A9).

A manager persona delegates a sub-task to a worker persona; DayPilot governs it.
These tests lock in the hard limits — no self, no cycles, depth ≤ 2, ≤ 3 workers,
≤ 10 child tasks, worker capability ≤ manager, same account only — and the
responsibility chain (You → Scarlett → Atlas).
"""
from __future__ import annotations

import uuid

from daypilot_knowledge.db import (
    HomePilotAgentLink,
    Task,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.homepilot import capability_matcher as matcher
from daypilot_orchestrator.homepilot import delegation


def _ws() -> str:
    return "ws-deleg-" + uuid.uuid4().hex[:8]


def _link(s, ws, name, caps, account="user:ana"):
    link = HomePilotAgentLink(
        workspace_id=ws, connection_id="c1", homepilot_project_id="p-" + name,
        name=name, enabled=True, status="available", account_ref=account,
        capabilities_json=caps,
    )
    s.add(link)
    s.flush()
    return link


# --- capability matcher -----------------------------------------------------

def test_matcher_prefers_exact_capability():
    cands = [
        matcher.Candidate("a", "Atlas", "Researcher", ["research", "writing"]),
        matcher.Candidate("b", "Bardo", "Coder", ["coding"]),
    ]
    assert matcher.match_worker(cands, "coding").link_id == "b"
    assert matcher.match_worker(cands, "research").link_id == "a"


def test_matcher_returns_none_when_no_signal():
    cands = [matcher.Candidate("a", "Atlas", "Researcher", ["research"])]
    assert matcher.match_worker(cands, "welding") is None


# --- delegation happy path + chain ------------------------------------------

def test_manager_delegates_to_worker_and_chain_is_built(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        scarlett = _link(s, ws, "Scarlett", ["management", "coding"])
        _link(s, ws, "Atlas", ["coding"])
        res = delegation.delegate(s, ws, scarlett, title="Write the script", capability="coding")
        assert res.code == "delegated" and res.worker_name == "Atlas" and res.depth == 2
        child = s.get(Task, res.child_task_id)
        assert child.assigned_agent_link_id != scarlett.id
        assert child.manager_agent_link_id == scarlett.id and child.status != "completed"
        chain = delegation.responsibility_chain(s, ws, child.assigned_agent_link_id)
        assert chain == ["You", "Scarlett", "Atlas"]


# --- safety limits ----------------------------------------------------------

def test_no_self_delegation(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        solo = _link(s, ws, "Solo", ["coding"])
        # Only agent available is the manager → no eligible worker.
        res = delegation.delegate(s, ws, solo, title="x", capability="coding")
        assert res.code == "rejected" and res.reason == "no_worker"


def test_depth_capped_at_two(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        a = _link(s, ws, "A", ["x"])
        b = _link(s, ws, "B", ["x"])
        _link(s, ws, "C", ["x"])
        r1 = delegation.delegate(s, ws, a, title="t1", capability="x")  # depth 2
        assert r1.code == "delegated" and r1.worker_name == "B"
        # B (now at depth 2) tries to delegate again → depth 3 > limit.
        r2 = delegation.delegate(s, ws, b, title="t2", capability="x")
        assert r2.code == "rejected" and r2.reason == "max_depth"


def test_no_cycles(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        a = _link(s, ws, "A", ["x"])
        b = _link(s, ws, "B", ["x"])
        delegation.delegate(s, ws, a, title="t", capability="x")  # A → B
        # B tries to delegate back to A: A is B's ancestor → excluded; only A left
        # as candidate → no worker (and never a cycle).
        res = delegation.delegate(s, ws, b, title="back", capability="x")
        assert res.code == "rejected" and res.reason in ("no_worker", "max_depth")


def test_worker_capped_at_three(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        # Manager holds four skills; each worker has a distinct one, so four
        # delegations pick four DISTINCT workers — the 4th trips the worker cap.
        mgr = _link(s, ws, "Mgr", ["c1", "c2", "c3", "c4"])
        parent = Task(workspace_id=ws, title="parent", owner="agent", assigned_agent_link_id=mgr.id)
        s.add(parent)
        s.flush()
        for name, cap in (("W1", "c1"), ("W2", "c2"), ("W3", "c3"), ("W4", "c4")):
            _link(s, ws, name, [cap])
        results = [delegation.delegate(s, ws, mgr, title=f"t{cap}", capability=cap, parent_task=parent)
                   for cap in ("c1", "c2", "c3", "c4")]
        assert sum(r.code == "delegated" for r in results) == 3   # 4th distinct worker blocked
        assert any(r.reason == "max_workers" for r in results)


def test_worker_capability_cannot_exceed_manager(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        mgr = _link(s, ws, "Mgr", ["writing"])       # manager can't do "coding"
        _link(s, ws, "Coder", ["coding"])
        res = delegation.delegate(s, ws, mgr, title="hack", capability="coding")
        assert res.code == "rejected" and res.reason == "exceeds_manager"


def test_delegation_stays_within_account(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        mgr = _link(s, ws, "Mgr", ["x"], account="user:ana")
        _link(s, ws, "Other", ["x"], account="user:bob")   # a DIFFERENT account
        res = delegation.delegate(s, ws, mgr, title="t", capability="x")
        assert res.code == "rejected" and res.reason == "no_worker"  # never crosses accounts


def test_delegation_deferred_when_flag_off(monkeypatch):
    """With DELEGATION off, a delegate.request directive is deferred (not acted
    on) — mapping never creates a cross-agent task behind the flag's back."""
    from daypilot_orchestrator.homepilot import task_mapper
    from daypilot_orchestrator.homepilot.directives import validate_directives
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.delenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", raising=False)
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        mgr = _link(s, ws, "Mgr", ["x"])
        _link(s, ws, "Worker", ["x"])
        v = validate_directives({"items": [{"type": "delegate.request", "title": "hand off", "capability": "x"}]})
        res = task_mapper.apply_directives(s, ws, mgr, v)
        assert res.delegations == [] and "delegate.request" in res.deferred


def test_endpoint_exposes_delegation_chain(monkeypatch):
    """The workspace can read an agent's delegation chains from its own endpoint."""
    import json
    from pathlib import Path
    from fastapi.testclient import TestClient
    from app import homepilot_platform as hp
    from app.main import app
    from daypilot_orchestrator.homepilot.client import HealthResult

    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_DELEGATION_ENABLED", "true")
    client = TestClient(app)
    ws = _ws()

    fixdir = Path(__file__).resolve().parent / "fixtures" / "homepilot"
    projects = json.loads((fixdir / "projects.json").read_text())["projects"]
    models = [m["id"] for m in json.loads((fixdir / "models.json").read_text())["data"]]

    class _Disc:
        def health(self):
            return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})
        def list_projects(self):
            return projects
        def list_models(self):
            return models
        def identity(self):
            return {"account_ref": "user:ana", "account_label": "Ana", "authenticated": True, "scope": "account"}

    monkeypatch.setattr(hp, "_client_for", lambda row: _Disc())
    conn = client.post("/v1/homepilot/connections", json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "k"}).json()["connection"]
    client.post(f"/v1/homepilot/connections/{conn['id']}/sync", json={"workspaceId": ws})
    profiles = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]
    scar = next(p for p in profiles if p["name"] == "Scarlett")
    atlas = next(p for p in profiles if p["name"] == "Atlas")
    for p in (scar, atlas):
        client.patch(f"/v1/agents/profiles/{p['id']}", json={"workspaceId": ws, "enabled": True})

    # Scarlett delegates to Atlas directly (Scarlett's persona has broad caps).
    with session_scope(create_engine_from_settings()) as s:
        mgr = s.get(HomePilotAgentLink, scar["id"])
        mgr.capabilities_json = ["research"]
        worker = s.get(HomePilotAgentLink, atlas["id"])
        worker.capabilities_json = ["research"]
        worker.status = "available"  # Atlas isn't shared in the fixture; make it reachable
        res = delegation.delegate(s, ws, mgr, title="Look into it", capability="research")
        assert res.code == "delegated"

    r = client.get(f"/v1/agents/profiles/{scar['id']}/delegations?workspaceId={ws}")
    assert r.status_code == 200
    chains = [d["chain"] for d in r.json()["delegations"]]
    assert ["You", "Scarlett", "Atlas"] in chains
