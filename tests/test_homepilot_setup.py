"""HomePilot setup: enabled-by-default status machine + detect/test + SSRF guard.

The integration is a first-class onboarding experience: with nothing connected it
reports ``not_connected`` (never an error), and only an explicit admin lock makes
it ``admin_disabled``. Detection and connection-testing happen on the backend and
never echo the API key or reach cloud-metadata addresses.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app import homepilot_setup as hp_setup
from app.main import app
from daypilot_orchestrator.homepilot.client import HealthResult

client = TestClient(app)


def _ws() -> str:
    return "ws-hp-setup-" + uuid.uuid4().hex[:8]


# --- status machine ---------------------------------------------------------

def test_status_not_connected_by_default(monkeypatch):
    monkeypatch.delenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", raising=False)
    r = client.get(f"/v1/homepilot/setup/status?workspaceId={_ws()}")
    assert r.status_code == 200
    data = r.json()
    assert data["featureEnabled"] is True
    assert data["adminLocked"] is False
    assert data["connectionState"] == "not_connected"
    assert data["installWizardAvailable"] is True
    assert data["connection"] is None


def test_status_admin_locked(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "false")
    r = client.get(f"/v1/homepilot/setup/status?workspaceId={_ws()}")
    # Reachable even under the lock, so the UI can show the right message.
    assert r.status_code == 200
    data = r.json()
    assert data["featureEnabled"] is False
    assert data["adminLocked"] is True
    assert data["connectionState"] == "admin_disabled"
    # No variable name leaks into the payload.
    assert "DAYPILOT_HOMEPILOT_RUNTIME_ENABLED" not in r.text


def test_status_connected_reports_agent_count(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()

    class _Fake:
        def health(self):
            return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

        def identity(self):
            return None

        def capabilities(self):
            return {"bridge_version": "1"}

    monkeypatch.setattr("app.homepilot_platform._client_for", lambda row: _Fake())
    r = client.post("/v1/homepilot/connections",
                    json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "sekret-99"})
    assert r.status_code == 200 and r.json()["code"] == "connected"
    assert "sekret-99" not in r.text  # the key is never returned

    resp = client.get(f"/v1/homepilot/setup/status?workspaceId={ws}")
    status = resp.json()
    assert status["connectionState"] == "connected"
    assert status["connection"]["apiUrl"] == "http://homepilot:7860/api"
    # The gallery/browser URL is browser-reachable: the Docker-internal "homepilot"
    # host is translated to localhost (the browser can't resolve the service name).
    assert status["connection"]["browserUrl"] == "http://localhost:7860"
    assert status["connection"]["agentCount"] == 0  # connected, no agents synced yet
    assert "sekret-99" not in resp.text


# --- detection --------------------------------------------------------------

def test_detect_finds_a_reachable_candidate(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")

    def fake_health(self):
        # Only the loopback 7860 desktop candidate answers on /health.
        if self.base_url.startswith("http://127.0.0.1:7860"):
            return HealthResult(reachable=True, status_code=200, payload={"version": "3.1"})
        return HealthResult(reachable=False, error="connection_refused")

    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health", fake_health)
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_models", lambda self: [])
    r = client.post("/v1/homepilot/setup/detect")
    assert r.status_code == 200
    data = r.json()
    assert data["detected"] is True
    assert data["instance"]["apiUrl"] == "http://127.0.0.1:7860/api"
    assert data["instance"]["installationType"] == "desktop"
    assert data["instance"]["version"] == "3.1"


def test_detect_finds_compose_via_models_only(monkeypatch):
    # The compose/source build answers on :8000 /v1/models even if /health is
    # absent — the detector must still find it (the OllaBridge-style probe).
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health",
                        lambda self: HealthResult(reachable=False, error="connection_refused"))

    def fake_models(self):
        return ["persona:assistant"] if self.base_url == "http://127.0.0.1:8000" else []

    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_models", fake_models)
    data = client.post("/v1/homepilot/setup/detect").json()
    assert data["detected"] is True
    assert data["instance"]["apiUrl"] == "http://127.0.0.1:8000"
    assert data["instance"]["installationType"] == "docker_compose"


def test_detect_none_when_nothing_answers(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health",
                        lambda self: HealthResult(reachable=False, error="connection_refused"))
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_models", lambda self: [])
    data = client.post("/v1/homepilot/setup/detect").json()
    assert data["detected"] is False and data["instance"] is None
    assert len(data["probes"]) == len(hp_setup.candidates()) and len(data["probes"]) >= 8


def test_candidates_cover_both_ports_and_include_discovered_hosts():
    cands = hp_setup.candidates()
    apis = {c[0] for c in cands}
    # Both port profiles (desktop 7860/api, compose 8000) for loopback.
    assert "http://127.0.0.1:7860/api" in apis
    assert "http://127.0.0.1:8000" in apis
    # The Docker service name + host alias are always tried.
    assert "http://homepilot:8000" in apis
    assert "http://host.docker.internal:8000" in apis
    # Discovered gateways (WSL2/Docker) are appended when present.
    for host in hp_setup._discovered_hosts():
        assert f"http://{host}:8000" in apis


# --- connection test (checklist) --------------------------------------------

def test_test_address_checklist(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")

    def fake_health(self):
        return HealthResult(reachable=True, status_code=200, payload={"version": "3.2"})

    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health", fake_health)
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_projects",
                        lambda self: [{"id": "p1", "project_type": "persona"}])
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_models",
                        lambda self: ["persona:p1"])
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.capabilities",
                        lambda self: {"bridge_version": "1"})

    r = client.post("/v1/homepilot/setup/test",
                    json={"baseUrl": "http://homepilot:7860/api", "apiKey": "secret-key"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["code"] == "connected"
    keys = {c["key"]: c["ok"] for c in data["checks"]}
    assert keys["reachable"] and keys["authenticated"] and keys["personas"] and keys["chat"]
    assert data["personaCount"] == 1 and data["chatCount"] == 1
    assert data["chatMode"] == "bridge" and data["version"] == "3.2"
    assert "secret-key" not in r.text  # the key is never echoed


def test_test_address_reports_auth_failure(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health",
                        lambda self: HealthResult(reachable=True, status_code=401, error="unauthorized"))
    data = client.post("/v1/homepilot/setup/test",
                       json={"baseUrl": "http://homepilot:7860/api", "apiKey": "bad"}).json()
    assert data["ok"] is False and data["code"] == "unauthorized"
    keys = {c["key"]: c["ok"] for c in data["checks"]}
    assert keys["reachable"] is True and keys["authenticated"] is False


# --- SSRF guard (unit) ------------------------------------------------------

def test_ssrf_guard_blocks_metadata_and_allows_local():
    assert hp_setup._ssrf_ok("http://127.0.0.1:7860/api") is True
    assert hp_setup._ssrf_ok("http://homepilot:7860/api") is True
    assert hp_setup._ssrf_ok("https://homepilot.example.com/api") is True
    # Cloud instance-metadata + link-local are always blocked.
    assert hp_setup._ssrf_ok("http://169.254.169.254/latest/meta-data") is False
    assert hp_setup._ssrf_ok("http://100.100.100.200/") is False
    # Private/loopback blocked only when the caller opts out.
    assert hp_setup._ssrf_ok("http://192.168.1.50:7860/api", allow_private=False) is False
    assert hp_setup._ssrf_ok("http://127.0.0.1:7860/api", allow_private=False) is False


def test_test_address_rejects_blocked_address(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    data = client.post("/v1/homepilot/setup/test",
                       json={"baseUrl": "http://169.254.169.254/latest"}).json()
    assert data["ok"] is False and data["code"] == "blocked_address"


# --- connection preferences -------------------------------------------------

def _connect(monkeypatch, ws: str) -> str:
    class _Fake:
        def health(self):
            return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

        def identity(self):
            return None

        def capabilities(self):
            return None

    monkeypatch.setattr("app.homepilot_platform._client_for", lambda row: _Fake())
    r = client.post("/v1/homepilot/connections",
                    json={"workspaceId": ws, "baseUrl": "http://homepilot:7860/api", "apiKey": "k"})
    return r.json()["connection"]["id"]


def test_prefs_default_and_persist(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()
    conn_id = _connect(monkeypatch, ws)

    # Defaults surfaced in setup/status.
    prefs = client.get(f"/v1/homepilot/setup/status?workspaceId={ws}").json()["connection"]["prefs"]
    assert prefs["autoSync"] is True and prefs["showOffline"] is True
    assert prefs["allowDelegation"] is False and prefs["syncIntervalMinutes"] == 15

    # PATCH persists a change; the permanent approval rule is never a preference.
    r = client.patch(f"/v1/homepilot/connections/{conn_id}",
                     json={"workspaceId": ws, "showOffline": False, "allowDelegation": True, "syncIntervalMinutes": 30})
    assert r.status_code == 200
    got = r.json()["connection"]["prefs"]
    assert got["showOffline"] is False and got["allowDelegation"] is True and got["syncIntervalMinutes"] == 30

    # The change survives a fresh read.
    again = client.get(f"/v1/homepilot/setup/status?workspaceId={ws}").json()["connection"]["prefs"]
    assert again["showOffline"] is False and again["allowDelegation"] is True


def test_show_offline_pref_filters_profiles(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()
    conn_id = _connect(monkeypatch, ws)

    # Seed one offline + one available agent on this connection.
    from daypilot_knowledge.db import HomePilotAgentLink, create_engine_from_settings, session_scope
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        for name, st in (("Ghost", "offline"), ("Live", "available")):
            s.add(HomePilotAgentLink(workspace_id=ws, connection_id=conn_id, account_ref="key:x",
                                     homepilot_project_id=name, homepilot_model_id=f"persona:{name}",
                                     name=name, enabled=True, status=st))

    names = {p["name"] for p in client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]}
    assert names == {"Ghost", "Live"}  # showOffline defaults on

    client.patch(f"/v1/homepilot/connections/{conn_id}", json={"workspaceId": ws, "showOffline": False})
    names = {p["name"] for p in client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]}
    assert names == {"Live"}  # offline agent hidden when the pref is off


def test_patch_connection_404_for_unknown(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    r = client.patch("/v1/homepilot/connections/nope", json={"workspaceId": _ws(), "showOffline": False})
    assert r.status_code == 404


# --- browser-reachable gallery URL (Open Gallery must never 404) -------------

def test_browser_url_is_reachable_across_topologies():
    from app import homepilot_platform as hp
    # Docker service name + API port → localhost + UI port (7860 desktop/container).
    assert hp._browser_url("http://homepilot:7860/api") == "http://localhost:7860"
    assert hp._browser_url("http://host.docker.internal:7860/api") == "http://localhost:7860"
    # Compose/source: API :8000 → human UI :3000.
    assert hp._browser_url("http://localhost:8000") == "http://localhost:3000"
    assert hp._browser_url("http://127.0.0.1:8000") == "http://127.0.0.1:3000"
    # A bind-all host is not browser-reachable either.
    assert hp._browser_url("http://0.0.0.0:8000") == "http://localhost:3000"
    # A real remote host is kept (only the port is mapped).
    assert hp._browser_url("http://192.168.1.50:8000") == "http://192.168.1.50:3000"
    # An explicit stored UI URL wins and is host-sanitized but not port-mapped.
    assert hp._browser_url("http://homepilot:8000", "http://homepilot:3000") == "http://localhost:3000"


def test_add_info_gallery_url_is_browser_reachable(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    ws = _ws()
    # No connection yet → "Open Gallery" leads to the public community gallery
    # (always reachable), never the internal "homepilot" host.
    info = client.get(f"/v1/homepilot/add-info?workspaceId={ws}").json()
    assert "homepilot:7860" not in info["galleryUrl"]
    assert info["galleryUrl"] == "https://ruslanmv.com/HomePilot/gallery.html"

    # After connecting with an explicit browser URL, that (sanitized) URL is used.
    class _Fake:
        def health(self):
            return HealthResult(reachable=True, status_code=200, payload={"status": "ok"})

        def identity(self):
            return None

        def capabilities(self):
            return None

    monkeypatch.setattr("app.homepilot_platform._client_for", lambda row: _Fake())
    client.post("/v1/homepilot/connections",
                json={"workspaceId": ws, "baseUrl": "http://homepilot:8000",
                      "apiKey": "k", "browserUrl": "http://localhost:3000"})
    info = client.get(f"/v1/homepilot/add-info?workspaceId={ws}").json()
    assert info["galleryUrl"] == "http://localhost:3000"


def test_detect_browser_url_translates_docker_service_name(monkeypatch):
    # The Docker single-container answers as the "homepilot" service; the detected
    # browserUrl must be browser-reachable (localhost), not the service name.
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")

    def fake_health(self):
        return HealthResult(reachable=True, status_code=200, payload={"version": "3.0"}) \
            if self.base_url.startswith("http://homepilot:7860") else HealthResult(reachable=False, error="x")

    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.health", fake_health)
    monkeypatch.setattr("daypilot_orchestrator.homepilot.client.HomePilotClient.list_models", lambda self: [])
    inst = client.post("/v1/homepilot/setup/detect").json()["instance"]
    assert inst["apiUrl"] == "http://homepilot:7860/api"
    assert inst["browserUrl"] == "http://localhost:7860"
    assert inst["installationType"] == "single_container"
