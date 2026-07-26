"""HomePilot agent chat bridge — turn endpoint + session persistence (Batch A6).

Covers: a real turn round-trips and persists both sides, propose-only is always
sent, a legacy (non-bridge) HomePilot degrades to chat-only, mixed-agent
conversations never cross, chat is gated by the CHAT flag, and the user's
message survives a remote failure.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import homepilot_platform as hp
from app.main import app
from daypilot_orchestrator.homepilot.client import HealthResult

client = TestClient(app)
FIX = Path(__file__).resolve().parent / "fixtures" / "homepilot"


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ws() -> str:
    return "ws-hpchat-" + uuid.uuid4().hex[:8]


class _FakeRuntime:
    """A bridge-aware (or legacy) HomePilot. Records every persona_chat call so
    tests can assert the model, tool mode, and stable session id."""

    def __init__(self, projects, models, *, bridge: bool = True):
        self._p, self._m, self._bridge = projects, models, bridge
        self.calls: list[dict] = []

    def health(self) -> HealthResult:
        return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

    def list_projects(self):
        return self._p

    def list_models(self):
        return self._m

    def persona_chat(self, model, messages, *, tool_mode=None, session_id=None, include_media=True):
        self.calls.append({
            "model": model,
            "tool_mode": getattr(tool_mode, "value", tool_mode),
            "session_id": session_id,
            "messages": messages,
        })
        last = messages[-1]["content"] if messages else ""
        resp = {"choices": [{"message": {"role": "assistant", "content": f"Reply to: {last}"}}]}
        if self._bridge:
            resp["x_directives"] = {"version": 1, "tool_mode": "propose", "items": [
                {"type": "task.create", "title": "Draft it"},
                {"type": "daypilot.action.propose", "capability": "email.send", "summary": "Email the team"},
            ]}
            resp["x_homepilot"] = {"bridge_version": 1, "tool_mode": tool_mode.value if tool_mode else None,
                                   "session_id": session_id, "directive_count": 2}
        return resp


def _enable(monkeypatch, ws: str, fake: _FakeRuntime, name: str = "Scarlett") -> str:
    """Connect + sync + enable one agent, returning its link id."""
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_CHAT_ENABLED", "true")
    monkeypatch.setattr(hp, "_client_for", lambda row: fake)

    conn = client.post("/v1/homepilot/connections", json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "k"})
    conn_id = conn.json()["connection"]["id"]
    client.post(f"/v1/homepilot/connections/{conn_id}/sync", json={"workspaceId": ws})
    profiles = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]
    link = next(p for p in profiles if p["name"] == name)
    client.patch(f"/v1/agents/profiles/{link['id']}", json={"workspaceId": ws, "enabled": True})
    return link["id"]


def test_turn_round_trips_persists_and_proposes(monkeypatch):
    ws = _ws()
    fake = _FakeRuntime(_fixture("projects.json")["projects"],
                        [m["id"] for m in _fixture("models.json")["data"]])
    link_id = _enable(monkeypatch, ws, fake)

    r = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Plan my day"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "bridge" and data["proposals"] == 1  # one external-write proposal
    assert data["applied"]["counts"]["created"] == 2  # task.create + the proposal's waiting task
    assert data["applied"]["counts"]["approvals"] == 1
    assert data["reply"]["role"] == "assistant" and "Plan my day" in data["reply"]["body"]

    # Always propose-only, addressing the persona model, with a stable session id.
    assert fake.calls[-1]["tool_mode"] == "propose"
    assert fake.calls[-1]["model"] == "persona:scarlett-project-id"
    assert fake.calls[-1]["session_id"]  # non-empty external session id

    # Both sides persisted and resumable.
    sess = client.get(f"/v1/agents/profiles/{link_id}/session?workspaceId={ws}").json()
    roles = [m["role"] for m in sess["messages"]]
    assert roles == ["user", "assistant"]
    assert sess["messages"][0]["body"] == "Plan my day"


def test_legacy_homepilot_degrades_to_chat_only(monkeypatch):
    ws = _ws()
    fake = _FakeRuntime(_fixture("projects.json")["projects"],
                        [m["id"] for m in _fixture("models.json")["data"]], bridge=False)
    link_id = _enable(monkeypatch, ws, fake)

    r = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "chat_only" and data["proposals"] == 0
    assert data["reply"]["body"]  # a plain reply still comes through


def test_mixed_agent_conversations_never_cross(monkeypatch):
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    models = [m["id"] for m in _fixture("models.json")["data"]]
    fake = _FakeRuntime(projects, models)
    scar = _enable(monkeypatch, ws, fake, name="Scarlett")
    atlas = _enable(monkeypatch, ws, fake, name="Atlas")

    client.post(f"/v1/agents/profiles/{scar}/turn", json={"workspaceId": ws, "message": "Scarlett only"})
    client.post(f"/v1/agents/profiles/{atlas}/turn", json={"workspaceId": ws, "message": "Atlas only"})

    s_msgs = client.get(f"/v1/agents/profiles/{scar}/session?workspaceId={ws}").json()["messages"]
    a_msgs = client.get(f"/v1/agents/profiles/{atlas}/session?workspaceId={ws}").json()["messages"]
    s_bodies = " ".join(m["body"] for m in s_msgs)
    a_bodies = " ".join(m["body"] for m in a_msgs)
    assert "Scarlett only" in s_bodies and "Atlas only" not in s_bodies
    assert "Atlas only" in a_bodies and "Scarlett only" not in a_bodies


def test_turn_404_when_chat_flag_off(monkeypatch):
    ws = _ws()
    fake = _FakeRuntime(_fixture("projects.json")["projects"],
                        [m["id"] for m in _fixture("models.json")["data"]])
    link_id = _enable(monkeypatch, ws, fake)
    # Chat is on by default; an admin can pin it off by setting the flag falsey.
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_CHAT_ENABLED", "false")  # master on, chat off
    r = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Hi"})
    assert r.status_code == 404


def test_proposal_flows_through_approval_center_and_executes(monkeypatch):
    """A8 end-to-end: a turn proposes an email → the workspace shows a waiting
    task → approving it in the Approval Center executes it and the task lifecycle
    reaches completed."""
    ws = _ws()
    fake = _FakeRuntime(_fixture("projects.json")["projects"],
                        [m["id"] for m in _fixture("models.json")["data"]])
    link_id = _enable(monkeypatch, ws, fake)

    turn = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Email the team"}).json()
    assert turn["proposals"] == 1
    approval_id = turn["applied"]["approvals"][0]

    # The workspace surfaces the agent's tasks with a lifecycle.
    tasks = client.get(f"/v1/agents/profiles/{link_id}/tasks?workspaceId={ws}").json()["tasks"]
    waiting = next(t for t in tasks if t["lifecycle"] == "awaiting")
    assert waiting["status"] == "waiting_for_approval" and waiting["approvalId"] == approval_id

    # Approve it in the Approval Center → DayPilot executes via its integration.
    decided = client.post(f"/v1/approvals/{approval_id}/decide", json={"decision": "approve"})
    assert decided.status_code == 200
    assert decided.json().get("agentExecution", {}).get("lifecycle") == "completed"

    tasks2 = client.get(f"/v1/agents/profiles/{link_id}/tasks?workspaceId={ws}").json()["tasks"]
    done = next(t for t in tasks2 if t["capability"] == "email.send")
    assert done["lifecycle"] == "completed" and done["status"] == "completed"


def test_rejecting_a_proposal_executes_nothing(monkeypatch):
    ws = _ws()
    fake = _FakeRuntime(_fixture("projects.json")["projects"],
                        [m["id"] for m in _fixture("models.json")["data"]])
    link_id = _enable(monkeypatch, ws, fake)
    turn = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Email the team"}).json()
    approval_id = turn["applied"]["approvals"][0]

    decided = client.post(f"/v1/approvals/{approval_id}/decide", json={"decision": "reject", "reason": "no"})
    assert decided.json().get("agentExecution", {}).get("lifecycle") == "rejected"
    tasks = client.get(f"/v1/agents/profiles/{link_id}/tasks?workspaceId={ws}").json()["tasks"]
    rej = next(t for t in tasks if t["capability"] == "email.send")
    assert rej["lifecycle"] == "rejected" and rej["status"] != "completed"


def test_user_message_survives_remote_failure(monkeypatch):
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    models = [m["id"] for m in _fixture("models.json")["data"]]

    class _Down(_FakeRuntime):
        def persona_chat(self, *a, **k):
            raise httpx.ConnectError("refused")

    fake = _Down(projects, models)
    link_id = _enable(monkeypatch, ws, fake)

    r = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "Draft the email"})
    assert r.status_code == 502  # retryable
    # The user's message was still persisted — nothing they typed is lost.
    sess = client.get(f"/v1/agents/profiles/{link_id}/session?workspaceId={ws}").json()
    assert [m["role"] for m in sess["messages"]] == ["user"]
    assert sess["messages"][0]["body"] == "Draft the email"
