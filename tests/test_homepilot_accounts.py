"""HomePilot multi-account isolation (security).

Each DayPilot connection is bound to a specific HomePilot account (via the
identity endpoint, or a credential fingerprint for older HomePilot). Agents are
stamped with that account; a key/account change re-scopes rather than blending,
and a cloud connection is bound to the cloud account. These tests lock in that
one user's agents can never surface under another account.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app import homepilot_platform as hp
from app.main import app
from daypilot_knowledge.db import HomePilotAgentLink, create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot.client import HealthResult
from daypilot_orchestrator.homepilot.sync import sync_agents

client = TestClient(app)
FIX = Path(__file__).resolve().parent / "fixtures" / "homepilot"


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ws() -> str:
    return "ws-acct-" + uuid.uuid4().hex[:8]


class _Discovery:
    def __init__(self, projects, models, account_ref, kind="local"):
        self._p, self._m = projects, models
        self._account = account_ref
        self._kind = kind

    def health(self):
        return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

    def list_projects(self):
        return self._p

    def list_models(self):
        return self._m

    def identity(self):
        return {"account_ref": self._account, "account_label": self._account.title(),
                "authenticated": True, "scope": "account"}


def test_remote_kind_classifies_cloud_vs_local():
    assert hp._remote_kind("http://localhost:7860/api") == "local"
    assert hp._remote_kind("http://homepilot:7860/api") == "local"
    assert hp._remote_kind("https://homepilot.ruslanmv.com/api") == "cloud"
    assert hp._remote_kind("https://ruslanmv-homepilot.hf.space/api") == "cloud"


def test_connection_binds_to_account_and_never_leaks_key(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    models = [m["id"] for m in _fixture("models.json")["data"]]
    monkeypatch.setattr(hp, "_client_for", lambda row: _Discovery(projects, models, "user:ana"))

    r = client.post("/v1/homepilot/connections", json={
        "workspaceId": ws, "baseUrl": "https://homepilot.ruslanmv.com/api", "apiKey": "ana-secret",
    })
    conn = r.json()["connection"]
    assert conn["accountRef"] == "user:ana"       # bound to the HomePilot account
    assert conn["remoteKind"] == "cloud"          # cloud install detected
    assert "ana-secret" not in r.text and "api_key" not in r.text


def test_two_accounts_on_one_connection_never_blend(monkeypatch):
    """If the connection's key later authenticates as a DIFFERENT account, the
    previous account's agents are marked offline, never surfaced under the new
    account."""
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    models = [m["id"] for m in _fixture("models.json")["data"]]
    eng = create_engine_from_settings()

    # First sync as account Ana.
    with session_scope(eng) as s:
        sync_agents(s, ws, "conn-1", _Discovery(projects, models, "user:ana"), account_ref="user:ana")
    with session_scope(eng) as s:
        links = list(s.query(HomePilotAgentLink).filter_by(workspace_id=ws, connection_id="conn-1"))
        assert links and all(row.account_ref == "user:ana" for row in links)
        # Enable one so we can prove it gets pulled offline on the account switch.
        links[0].enabled = True
        links[0].status = "available"

    # The same connection now authenticates as Bob → Ana's agents go offline.
    with session_scope(eng) as s:
        sync_agents(s, ws, "conn-1", _Discovery(projects, models, "user:bob"), account_ref="user:bob")
    with session_scope(eng) as s:
        by_acct = {}
        for row in s.query(HomePilotAgentLink).filter_by(workspace_id=ws, connection_id="conn-1"):
            by_acct.setdefault(row.account_ref, []).append(row)
        # Bob's agents are the live set; every Ana link is offline.
        assert all(row.status == "offline" for row in by_acct.get("user:ana", []))
        assert any(row.status != "offline" for row in by_acct.get("user:bob", []))


def test_turn_refuses_agent_from_a_different_account(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_CHAT_ENABLED", "true")
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    models = [m["id"] for m in _fixture("models.json")["data"]]
    monkeypatch.setattr(hp, "_client_for", lambda row: _Discovery(projects, models, "user:ana"))

    conn = client.post("/v1/homepilot/connections", json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "k"}).json()["connection"]
    client.post(f"/v1/homepilot/connections/{conn['id']}/sync", json={"workspaceId": ws})
    link = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"][0]
    client.patch(f"/v1/agents/profiles/{link['id']}", json={"workspaceId": ws, "enabled": True})

    # Tamper: mark the link as belonging to a different account than the bound one.
    with session_scope(create_engine_from_settings()) as s:
        row = s.get(HomePilotAgentLink, link["id"])
        row.account_ref = "user:someone-else"

    r = client.post(f"/v1/agents/profiles/{link['id']}/turn", json={"workspaceId": ws, "message": "hi"})
    assert r.status_code == 409  # account_mismatch — refused
