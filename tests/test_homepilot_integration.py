"""HomePilot agents integration — foundation tests (PRs 01–04).

Covers the frozen contract, the HTTP client (mock transport), persona
normalization + sync (create refs, mark shared, mark removed offline), and the
gateway connection/profile endpoints (gated by the runtime flag, secret-safe).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app import homepilot_platform as hp
from app.main import app
from daypilot_knowledge.db import create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot import contracts
from daypilot_orchestrator.homepilot.client import HealthResult, HomePilotClient
from daypilot_orchestrator.homepilot.sync import sync_agents

client = TestClient(app)
FIX = Path(__file__).resolve().parent / "fixtures" / "homepilot"


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ws() -> str:
    return "ws-hp-" + uuid.uuid4().hex[:8]


# --- contract ---------------------------------------------------------------

def test_feature_flags_default_off_and_gate_on_master(monkeypatch):
    for f in contracts.HomePilotFeature:
        monkeypatch.delenv(f.value, raising=False)
    assert contracts.runtime_enabled() is False
    assert contracts.feature_enabled(contracts.HomePilotFeature.SYNC) is False
    # Sync needs BOTH master + its own flag.
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    assert contracts.feature_enabled(contracts.HomePilotFeature.SYNC) is False
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    assert contracts.feature_enabled(contracts.HomePilotFeature.SYNC) is True


def test_contract_directives_and_persona_ids():
    assert "task.create" in contracts.ALLOWED_DIRECTIVES
    assert "daypilot.action.propose" in contracts.ALLOWED_DIRECTIVES
    assert "email.send" in contracts.CAPABILITIES
    assert contracts.persona_model_id("abc") == "persona:abc"
    assert contracts.is_persona_model("persona:abc") is True
    assert contracts.project_id_from_model("persona:abc") == "abc"
    assert contracts.ToolMode.PROPOSE.value == "propose"


# --- client (mock transport) ------------------------------------------------

def _mock_client() -> HomePilotClient:
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/health"):
            return httpx.Response(200, json=_fixture("health.json"))
        if p.endswith("/projects"):
            return httpx.Response(200, json=_fixture("projects.json"))
        if p.endswith("/v1/models"):
            return httpx.Response(200, json=_fixture("models.json"))
        if p.endswith("/v1/chat/completions"):
            # Echo the tool-mode header so the test can assert propose-only.
            return httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "x_tool_mode": request.headers.get("x-homepilot-tool-mode"),
                "x_client": request.headers.get("x-client-type"),
            })
        return httpx.Response(404)

    return HomePilotClient(base_url="http://homepilot:7860/api", api_key="hp-key",
                           transport=httpx.MockTransport(handler))


def test_client_discovery_and_propose_only_chat():
    c = _mock_client()
    health = c.health()
    assert health.reachable is True and health.status_code == 200
    projects = c.list_projects()
    assert any(p["id"] == "scarlett-project-id" for p in projects)
    models = c.list_models()
    assert "persona:scarlett-project-id" in models
    out = c.persona_chat("persona:scarlett-project-id", [{"role": "user", "content": "hi"}])
    assert out["x_tool_mode"] == "propose"   # DayPilot always proposes
    assert out["x_client"] == "daypilot"


def test_client_health_never_raises_offline():
    def boom(_req):
        raise httpx.ConnectError("refused")
    c = HomePilotClient(base_url="http://down:7860/api", transport=httpx.MockTransport(boom))
    assert c.health() == HealthResult(reachable=False, error="connection_refused")
    assert c.list_projects() == [] and c.list_models() == []


# --- sync (normalizer + upsert + offline) -----------------------------------

class _FakeDiscovery:
    def __init__(self, projects, models):
        self._p, self._m = projects, models

    def list_projects(self):
        return self._p

    def list_models(self):
        return self._m


def test_sync_creates_refs_marks_shared_and_offline():
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    model_ids = [m["id"] for m in _fixture("models.json")["data"]]
    eng = create_engine_from_settings()

    with session_scope(eng) as s:
        res = sync_agents(s, ws, "conn-1", _FakeDiscovery(projects, model_ids))
    # Two persona projects (Scarlett, Atlas); the document project is skipped.
    assert res["total"] == 2
    from daypilot_knowledge.db import HomePilotAgentLink
    with session_scope(eng) as s:
        links = {row.homepilot_project_id: row for row in s.query(HomePilotAgentLink).filter_by(workspace_id=ws)}
        assert set(links) == {"scarlett-project-id", "atlas-project-id"}
        scar = links["scarlett-project-id"]
        assert scar.name == "Scarlett" and scar.role == "Executive Secretary"
        assert scar.homepilot_model_id == "persona:scarlett-project-id"
        assert scar.enabled is False and scar.status == "disabled"   # disabled until enabled
        assert scar.snapshot_json["shared"] is True                  # Scarlett is on /v1/models
        assert links["atlas-project-id"].snapshot_json["shared"] is False  # Atlas isn't shared

    # Second sync with Scarlett removed from HomePilot → offline, not deleted.
    with session_scope(eng) as s:
        res2 = sync_agents(s, ws, "conn-1", _FakeDiscovery([projects[1], projects[2]], model_ids))
    assert res2["offline"] == 1
    with session_scope(eng) as s:
        from daypilot_knowledge.db import HomePilotAgentLink as L
        scar = s.query(L).filter_by(workspace_id=ws, homepilot_project_id="scarlett-project-id").one()
        assert scar.status == "offline"  # preserved, marked offline


# --- gateway endpoints ------------------------------------------------------

def test_endpoints_404_when_runtime_disabled(monkeypatch):
    monkeypatch.delenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", raising=False)
    assert client.get(f"/v1/agents/profiles?workspaceId={_ws()}").status_code == 404
    assert client.get(f"/v1/homepilot/connections?workspaceId={_ws()}").status_code == 404


def test_connect_sync_and_enable_profile(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    ws = _ws()

    projects = _fixture("projects.json")["projects"]
    model_ids = [m["id"] for m in _fixture("models.json")["data"]]

    class _Fake(_FakeDiscovery):
        def health(self):
            return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

    monkeypatch.setattr(hp, "_client_for", lambda row: _Fake(projects, model_ids))

    # Connect (secret held server-side; response is base host only, never the key).
    r = client.post("/v1/homepilot/connections", json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "top-secret"})
    assert r.status_code == 200 and r.json()["code"] == "connected"
    conn_id = r.json()["connection"]["id"]
    assert "top-secret" not in r.text

    # Sync references from HomePilot.
    sy = client.post(f"/v1/homepilot/connections/{conn_id}/sync", json={"workspaceId": ws})
    assert sy.status_code == 200 and sy.json()["total"] == 2

    # Profiles list — agents present but disabled by default.
    profiles = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]
    scar = next(p for p in profiles if p["name"] == "Scarlett")
    assert scar["enabled"] is False and scar["status"] == "disabled"

    # Enable Scarlett in DayPilot → available (she is shared).
    patched = client.patch(f"/v1/agents/profiles/{scar['id']}", json={"workspaceId": ws, "enabled": True}).json()
    assert patched["enabled"] is True and patched["status"] == "available"


def test_status_and_connection_never_leak_the_key(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()

    class _Fake:
        def health(self):
            return HealthResult(reachable=True, status_code=200)
    monkeypatch.setattr(hp, "_client_for", lambda row: _Fake())

    client.post("/v1/homepilot/connections", json={"workspaceId": ws, "apiKey": "sekret-key-xyz"})
    body = client.get(f"/v1/homepilot/connections?workspaceId={ws}").text
    assert "sekret-key-xyz" not in body and "api_key" not in body
