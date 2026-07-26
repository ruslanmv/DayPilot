"""Persistent remote-session mapping + failure behavior (Batch A11).

Locks in durable continuity (remote_session_id stays stable, remote
conversation id is captured + reused) and the honest-degradation failure matrix:
capability probe on connect (bridge vs legacy chat-only), HomePilot offline →
agents offline but local history served, timeout → message retained + retry.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import homepilot_platform as hp
from app.main import app
from daypilot_knowledge.db import ChatSession, create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot.client import HealthResult

client = TestClient(app)
FIX = Path(__file__).resolve().parent / "fixtures" / "homepilot"


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ws() -> str:
    return "ws-hps-" + uuid.uuid4().hex[:8]


class _Fake:
    def __init__(self, projects, models, *, bridge=True, timeout=False):
        self._p, self._m, self._bridge, self._timeout = projects, models, bridge, timeout
        self.sessions: list[str | None] = []

    def health(self):
        return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

    def list_projects(self):
        return self._p

    def list_models(self):
        return self._m

    def identity(self):
        return {"account_ref": "user:ana", "account_label": "Ana", "authenticated": True, "scope": "account"}

    def capabilities(self):
        return {"bridge_version": 1} if self._bridge else None

    def persona_chat(self, model, messages, *, tool_mode=None, session_id=None, include_media=True):
        self.sessions.append(session_id)
        if self._timeout:
            raise httpx.TimeoutException("slow")
        resp = {"id": "hp-conv-123", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        if self._bridge:
            resp["x_homepilot"] = {"bridge_version": 1, "session_id": session_id}
            resp["x_directives"] = {"version": 1, "tool_mode": "propose", "items": []}
        return resp


def _enable(monkeypatch, ws, fake, name="Scarlett"):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_CHAT_ENABLED", "true")
    monkeypatch.setattr(hp, "_client_for", lambda row: fake)
    conn = client.post("/v1/homepilot/connections", json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "k"}).json()
    conn_id = conn["connection"]["id"]
    client.post(f"/v1/homepilot/connections/{conn_id}/sync", json={"workspaceId": ws})
    link = next(p for p in client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"] if p["name"] == name)
    client.patch(f"/v1/agents/profiles/{link['id']}", json={"workspaceId": ws, "enabled": True})
    return conn["connection"], link["id"]


def test_connect_probes_bridge_capability(monkeypatch):
    ws = _ws()
    fake = _Fake(_fixture("projects.json")["projects"], [m["id"] for m in _fixture("models.json")["data"]], bridge=True)
    conn, _ = _enable(monkeypatch, ws, fake)
    assert conn["chatMode"] == "bridge"


def test_legacy_homepilot_probed_as_chat_only(monkeypatch):
    ws = _ws()
    fake = _Fake(_fixture("projects.json")["projects"], [m["id"] for m in _fixture("models.json")["data"]], bridge=False)
    conn, _ = _enable(monkeypatch, ws, fake)
    assert conn["chatMode"] == "chat_only"


def test_session_id_is_stable_and_conversation_id_captured(monkeypatch):
    ws = _ws()
    fake = _Fake(_fixture("projects.json")["projects"], [m["id"] for m in _fixture("models.json")["data"]])
    _, link_id = _enable(monkeypatch, ws, fake)

    client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "one"})
    client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "two"})
    # The same external session id is sent across turns (continuity).
    assert fake.sessions[0] and fake.sessions[0] == fake.sessions[1]
    # HomePilot's conversation id is captured once and persisted.
    with session_scope(create_engine_from_settings()) as s:
        row = s.query(ChatSession).filter_by(workspace_id=ws, kind="agent").one()
        assert row.remote_session_id and row.remote_conversation_id == "hp-conv-123"


def test_session_endpoint_reports_mode(monkeypatch):
    ws = _ws()
    fake = _Fake(_fixture("projects.json")["projects"], [m["id"] for m in _fixture("models.json")["data"]])
    _, link_id = _enable(monkeypatch, ws, fake)
    sess = client.get(f"/v1/agents/profiles/{link_id}/session?workspaceId={ws}").json()
    assert sess["mode"] == "bridge" and sess["degraded"] is False


def test_offline_serves_local_history_and_timeout_retains(monkeypatch):
    ws = _ws()
    fake = _Fake(_fixture("projects.json")["projects"], [m["id"] for m in _fixture("models.json")["data"]])
    _, link_id = _enable(monkeypatch, ws, fake)
    client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "remember this"})

    # HomePilot now times out — the message is retained and 504 asks for retry.
    slow = _Fake(fake._p, fake._m, timeout=True)
    monkeypatch.setattr(hp, "_client_for", lambda row: slow)
    r = client.post(f"/v1/agents/profiles/{link_id}/turn", json={"workspaceId": ws, "message": "will time out"})
    assert r.status_code == 504

    # The conversation (and the just-typed message) is still served from local history.
    sess = client.get(f"/v1/agents/profiles/{link_id}/session?workspaceId={ws}").json()
    bodies = " ".join(m["body"] for m in sess["messages"])
    assert "remember this" in bodies and "will time out" in bodies
