"""Backend-owned provider connections (Batch 2).

Verifies provider state is server-owned (not fabricated), local detection
returns specific error codes and never marks connected when Ollabridge is
absent, the SSRF guard rejects non-local URLs, secrets never appear in the
public view, connect-after-test persists, and active-provider selection
requires a connected provider.
"""
from __future__ import annotations

import uuid

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app import providers_platform as pp
from daypilot_knowledge.db import ProviderConnection, create_engine_from_settings, session_scope

client = TestClient(app)
ENGINE = create_engine_from_settings()


def _ws() -> str:
    return "ws-prov-" + uuid.uuid4().hex[:8]


def test_status_starts_unconfigured_and_never_fabricated():
    ws = _ws()
    body = client.get(f"/v1/providers/status?workspaceId={ws}").json()
    kinds = {c["kind"]: c for c in body["connections"]}
    assert set(kinds) == {"local", "ollabridge_cloud"}
    assert kinds["local"]["state"] == "unconfigured"
    assert kinds["local"]["active"] is False and body["active"] is None
    assert kinds["ollabridge_cloud"]["account"] is None


def test_ssrf_guard_rejects_non_local_urls():
    assert pp._is_allowed_local("http://localhost:11435/v1") is True
    assert pp._is_allowed_local("http://127.0.0.1:11435/v1") is True
    assert pp._is_allowed_local("http://192.168.1.5:11435/v1") is True
    assert pp._is_allowed_local("http://example.com/v1") is False
    assert pp._is_allowed_local("http://8.8.8.8/v1") is False


def test_local_test_url_not_allowed():
    ws = _ws()
    out = client.post("/v1/providers/local/test",
                      json={"workspaceId": ws, "baseUrl": "http://evil.example.com/v1"}).json()
    assert out["code"] == "invalid_response" and out.get("detail") == "url_not_allowed"


def test_local_absent_is_not_connected(monkeypatch):
    ws = _ws()
    # Simulate Ollabridge not running: connection refused.
    def refuse(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(pp.OllabridgeConnector, "ping", lambda self: (_ for _ in ()).throw(httpx.ConnectError("x")))
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))
    with session_scope(ENGINE) as s:
        out = pp.local_test(s, ws, "http://localhost:11435/v1", None)
    assert out["code"] == "connection_refused"
    assert out["connection"]["state"] == "offline" and out["connection"]["active"] is False


def _connected_probe(models):
    return lambda base, key: {
        "code": "connected", "latencyMs": 12.0, "models": list(models),
        "resolvedBaseUrl": pp.normalize_gateway_root(base) + "/v1",
    }


def test_local_connect_persists_after_successful_probe(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(pp, "_probe_local", _connected_probe(["llama3.1", "qwen2.5"]))
    with session_scope(ENGINE) as s:
        out = pp.local_connect(s, ws, "http://localhost:11435/v1", None)
    assert out["code"] == "connected"
    assert out["connection"]["modelsCount"] == 2 and out["connection"]["defaultModel"] == "llama3.1"
    with session_scope(ENGINE) as s:
        row = s.query(ProviderConnection).filter_by(workspace_id=ws, kind="local").one()
        assert row.state == "connected"


def test_set_active_requires_connected_provider(monkeypatch):
    ws = _ws()
    # Cloud is unconfigured -> activating it is refused.
    resp = client.patch("/v1/providers/active", json={"workspaceId": ws, "kind": "ollabridge_cloud"})
    assert resp.status_code == 409

    # Connect local, then activate it.
    monkeypatch.setattr(pp, "_probe_local", _connected_probe(["llama3.1"]))
    with session_scope(ENGINE) as s:
        pp.local_connect(s, ws, "http://localhost:11435/v1", None)
    ok = client.patch("/v1/providers/active", json={"workspaceId": ws, "kind": "local"})
    assert ok.status_code == 200 and ok.json()["active"] == "local"


def test_local_probe_normalizes_stored_v1_base(monkeypatch):
    """The stored base is http://localhost:11435/v1; the probe must hand
    _probe_one a root with /v1 stripped, so /v1/models resolves (no 404 →
    "not running" false negative)."""
    seen: dict = {}

    def fake_probe_one(root, key):
        seen["root"] = root
        return {"code": "connected", "latencyMs": 5.0, "models": ["llama3"]}

    monkeypatch.setattr(pp, "_probe_one", fake_probe_one)
    with session_scope(ENGINE) as s:
        out = pp.local_test(s, _ws(), "http://localhost:11435/v1", None)
    assert out["code"] == "connected"
    assert seen["root"] == "http://localhost:11435"  # /v1 stripped → no doubling


def _tiny_gateway(models_status: int, models_body: dict | None = None, health_body: dict | None = None):
    """A throwaway local gateway: public /health, gated/variable /v1/models."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/").endswith("/health"):
                body = _json.dumps(health_body or {"status": "ok", "nodes": 1}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.rstrip("/").endswith("/v1/models"):
                if models_status == 200:
                    body = _json.dumps(models_body or {"data": []}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(models_status)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_local_probe_health_first_reports_key_required_not_offline():
    """Regression for 'Ollabridge isn't running at that address': a healthy
    gateway that gates /v1/models behind a key (non-loopback / required mode) is
    reachable via public /health, so it must NOT be reported as offline."""
    srv, base = _tiny_gateway(models_status=401)
    try:
        no_key = pp._probe_local(base, None)
        with_key = pp._probe_local(base, "sk-ollabridge-wrong")
    finally:
        srv.shutdown()
    assert no_key["code"] == "key_required"   # reachable; just needs the key
    assert with_key["code"] == "unauthorized"  # a key was supplied but rejected


def test_wsl_host_fallbacks_prioritise_default_gateway(monkeypatch):
    """WSL2 fix: the eth0 default-route gateway (the Windows host) is tried
    first, ahead of the Docker alias, so a host-side gateway is reachable when
    localhost (the WSL VM) refuses."""
    monkeypatch.setattr(pp, "_default_route_gateway", lambda: "172.31.96.1")
    ips = pp._host_gateway_ips()
    assert ips[0] == "172.31.96.1"           # host first
    assert ips[-1] == "host.docker.internal"  # docker alias last
    # A loopback URL expands to include the host gateway as a candidate.
    cands = pp._loopback_candidates("http://localhost:11435")
    assert "http://172.31.96.1:11435" in cands
    assert cands[0] == "http://localhost:11435"  # original first


def test_default_route_gateway_parses_valid_ipv4_or_none():
    gw = pp._default_route_gateway()
    if gw is not None:
        import ipaddress as _ip
        _ip.ip_address(gw)  # raises if the little-endian decode is wrong


def test_local_probe_connected_when_models_listed():
    srv, base = _tiny_gateway(200, {"data": [{"id": "llama3"}, {"id": "qwen2.5"}]})
    try:
        res = pp._probe_local(base, None)
    finally:
        srv.shutdown()
    assert res["code"] == "connected" and res["models"] == ["llama3", "qwen2.5"]


def test_scan_ports_defaults_and_parsing(monkeypatch):
    monkeypatch.delenv("DAYPILOT_PROVIDER_PORT_SCAN", raising=False)
    assert pp._scan_ports() == list(range(8000, 8011))  # 8000–8010 inclusive
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", "8000,8001,8080")
    assert pp._scan_ports() == [8000, 8001, 8080]
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", "9000-9002")
    assert pp._scan_ports() == [9000, 9001, 9002]
    # A garbage value falls back rather than raising into the probe path.
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", "not-a-range")
    assert pp._scan_ports() == list(range(8000, 8011))


def test_port_scan_roots_are_localhost_only_and_exclude_the_configured_port(monkeypatch):
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", "8000-8002")
    roots = pp._port_scan_roots("http://localhost:8000")
    # The configured port is not re-probed; the rest of the range is.
    assert "http://localhost:8000" not in roots
    assert "http://localhost:8001" in roots and "http://localhost:8002" in roots
    # A non-loopback host is never port-scanned (that would be a real port sweep).
    assert pp._port_scan_roots("http://192.168.1.5:8000") == []


def test_local_probe_finds_a_gateway_on_a_nearby_port(monkeypatch):
    """The reported symptom: the configured port is dead, but a working gateway
    is one port over. The probe scans the bounded range and resolves to it."""
    srv, base = _tiny_gateway(200, {"data": [{"id": "llama3.1"}]})
    live_port = srv.server_address[1]
    # Point the configured URL at a port nothing is listening on, and put the
    # live gateway's real port in the scan range.
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", str(live_port))
    try:
        res = pp._probe_local("http://localhost:9/v1", None)
    finally:
        srv.shutdown()
    assert res["code"] == "connected" and res["models"] == ["llama3.1"]
    # And it persisted the port that actually answered, not the dead one.
    assert res["resolvedBaseUrl"] == f"http://localhost:{live_port}/v1"


def test_port_scan_is_not_reached_when_the_configured_port_works(monkeypatch):
    """The scan must be a fallback, never an always-on sweep: a working primary
    short-circuits before any scan port is touched."""
    scanned: list[str] = []
    real_probe = pp._probe_one

    def spy(root, key, timeout=5.0):
        scanned.append(root)
        return real_probe(root, key, timeout)

    srv, base = _tiny_gateway(200, {"data": [{"id": "llama3.1"}]})
    monkeypatch.setenv("DAYPILOT_PROVIDER_PORT_SCAN", "8000-8010")
    monkeypatch.setattr(pp, "_probe_one", spy)
    try:
        res = pp._probe_local(base, None)
    finally:
        srv.shutdown()
    assert res["code"] == "connected"
    # Only the configured host was probed; no 8000–8010 candidate was touched.
    assert all(":800" not in r and ":801" not in r for r in scanned)


def test_cloud_auth_root_and_web_links_never_double_v1():
    assert not pp._cloud_auth_root().endswith("/v1")
    login = pp.cloud_web_login_url()
    assert login.endswith("/login") and "/v1/v1" not in login
    assert pp.cloud_web_register_url().endswith("/register")


def test_status_exposes_cloud_web_login():
    body = client.get(f"/v1/providers/status?workspaceId={_ws()}").json()
    assert body["cloudLoginUrl"].endswith("/login")
    assert body["cloudRegisterUrl"].endswith("/register")


def test_public_view_never_leaks_secrets(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(pp, "_probe_local", _connected_probe(["llama3.1"]))
    with session_scope(ENGINE) as s:
        pp.local_connect(s, ws, "http://localhost:11435/v1", "sk-secret-key")
    body = client.get(f"/v1/providers/status?workspaceId={ws}").json()
    blob = str(body)
    assert "sk-secret-key" not in blob and "secret_reference" not in blob and "apiKey" not in blob


# ---- v2: read-only status, race-safe rows, API-key cloud, local model list ---

def test_status_is_read_only_and_creates_no_rows():
    """GET /status must never insert. Several first-load callers (Settings, the
    onboarding wizard, the assistant badge) run at once, and a read-then-insert
    on the unique (workspace, kind) index was the 500 behind the UI's
    "Couldn't load providers"."""
    ws = _ws()
    body = client.get(f"/v1/providers/status?workspaceId={ws}").json()
    assert {c["kind"] for c in body["connections"]} == {"local", "ollabridge_cloud"}
    assert all(c["state"] == "unconfigured" and c["authMethod"] is None for c in body["connections"])
    with session_scope(ENGINE) as s:
        assert s.query(ProviderConnection).filter_by(workspace_id=ws).count() == 0


def test_get_or_create_adopts_a_concurrently_inserted_row(monkeypatch):
    """The first-load race, made deterministic: another request commits the
    same (workspace, kind) row between our SELECT and our INSERT. We must adopt
    that row instead of raising, and the session must stay usable."""
    from sqlalchemy.orm import Session as _Session

    ws = _ws()
    real_flush = _Session.flush
    fired = {"done": False}

    def racing_flush(self, *a, **k):
        if not fired["done"]:
            fired["done"] = True
            with session_scope(ENGINE) as other:  # a different request wins the insert
                other.add(ProviderConnection(workspace_id=ws, kind="local", state="connected",
                                             base_url="http://localhost:11435/v1"))
        return real_flush(self, *a, **k)

    monkeypatch.setattr(_Session, "flush", racing_flush)
    with session_scope(ENGINE) as s:
        row = pp._get_or_create(s, ws, "local")
        assert row.state == "connected"  # the winner's row, not a fresh duplicate
        assert pp._get_or_create(s, ws, "ollabridge_cloud").kind == "ollabridge_cloud"
    with session_scope(ENGINE) as s:
        assert s.query(ProviderConnection).filter_by(workspace_id=ws, kind="local").count() == 1


def _tiny_cloud(models: list[str], expect_key: str):
    """A throwaway 'Ollabridge Cloud': public /health, Bearer-gated /v1/models."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=None):
            data = _json.dumps(body).encode() if body is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            path = self.path.rstrip("/")
            if path.endswith("/health"):
                self._send(200, {"status": "ok", "mode": "cloud"})
            elif path.endswith("/v1/models"):
                if self.headers.get("Authorization") == f"Bearer {expect_key}":
                    self._send(200, {"data": [{"id": m} for m in models]})
                else:
                    self._send(401, {"detail": "invalid key"})
            else:
                self._send(404)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def test_cloud_connect_key_stores_by_reference_and_lists_models(monkeypatch):
    srv, base = _tiny_cloud(["qwen2.5", "llama3.1"], "ob_test_good")
    monkeypatch.setattr(pp, "CLOUD_API_BASE", base)
    ws = _ws()
    try:
        out = client.post("/v1/providers/cloud/connect-key",
                          json={"workspaceId": ws, "apiKey": "ob_test_good"}).json()
        status_body = client.get(f"/v1/providers/status?workspaceId={ws}").json()
        activate = client.patch("/v1/providers/active", json={"workspaceId": ws, "kind": "ollabridge_cloud"})
    finally:
        srv.shutdown()
    assert out["code"] == "connected" and out["models"] == ["qwen2.5", "llama3.1"]
    conn = out["connection"]
    assert conn["state"] == "connected" and conn["modelsCount"] == 2 and conn["defaultModel"] == "qwen2.5"
    assert conn["authMethod"] == "api_key" and conn["account"]["displayName"] == "API key"
    # The key itself never leaves the server.
    assert "ob_test_good" not in str(out) and "ob_test_good" not in str(status_body)
    assert activate.status_code == 200  # a key-connected cloud can be activated


def test_cloud_connect_key_rejects_bad_or_missing_keys(monkeypatch):
    srv, base = _tiny_cloud(["qwen2.5"], "ob_test_good")
    monkeypatch.setattr(pp, "CLOUD_API_BASE", base)
    try:
        bad = client.post("/v1/providers/cloud/connect-key",
                          json={"workspaceId": _ws(), "apiKey": "ob_test_wrong"}).json()
    finally:
        srv.shutdown()
    assert bad["code"] == "unauthorized" and bad["connection"]["state"] == "unauthorized"
    empty = client.post("/v1/providers/cloud/connect-key", json={"workspaceId": _ws(), "apiKey": "  "}).json()
    assert empty["code"] == "key_required"


def test_local_models_lists_from_the_stored_connection():
    srv, base = _tiny_gateway(200, {"data": [{"id": "llama3.1"}, {"id": "deepseek-r1"}]})
    ws = _ws()
    try:
        with session_scope(ENGINE) as s:
            assert pp.local_connect(s, ws, base, None)["code"] == "connected"
        out = client.get(f"/v1/providers/local/models?workspaceId={ws}").json()
    finally:
        srv.shutdown()
    assert out["models"] == ["llama3.1", "deepseek-r1"] and out["state"] == "connected"
    assert out["gateway"] and out["gateway"]["status"] == "ok"
    # An unconfigured workspace answers calmly — no probe, no error.
    assert client.get(f"/v1/providers/local/models?workspaceId={_ws()}").json() == {
        "models": [], "state": "unconfigured", "defaultModel": None, "gateway": None,
    }


def test_local_recheck_reuses_the_stored_key(monkeypatch):
    """Re-check from Settings sends no key (the browser never holds it); the
    backend probes with the stored one so a key-protected gateway does not
    flip from connected to unauthorized on every re-check."""
    seen: dict = {}

    def fake_probe(base, key):
        seen["key"] = key
        return {"code": "connected", "latencyMs": 3.0, "models": ["m"],
                "resolvedBaseUrl": pp.normalize_gateway_root(base) + "/v1"}

    monkeypatch.setattr(pp, "_probe_local", fake_probe)
    ws = _ws()
    with session_scope(ENGINE) as s:
        pp.local_connect(s, ws, "http://localhost:11435/v1", "sk-ollabridge-stored")
    with session_scope(ENGINE) as s:
        out = pp.local_test(s, ws, "http://localhost:11435/v1", None)
    assert out["code"] == "connected" and seen["key"] == "sk-ollabridge-stored"


def test_default_model_rejects_unknown_provider():
    resp = client.patch("/v1/providers/default-model", json={"workspaceId": _ws(), "kind": "nope", "model": "x"})
    assert resp.status_code == 400


def test_local_connect_prefers_the_gateways_own_default_model():
    """Ollabridge announces its configured default model on /health; a fresh
    connection adopts it (when it is actually served) instead of whatever the
    model list happens to put first."""
    srv, base = _tiny_gateway(200, {"data": [{"id": "llama3.1"}, {"id": "deepseek-r1"}]},
                              health_body={"status": "ok", "default_model": "deepseek-r1"})
    ws = _ws()
    try:
        with session_scope(ENGINE) as s:
            out = pp.local_connect(s, ws, base, None)
    finally:
        srv.shutdown()
    assert out["code"] == "connected" and out["connection"]["defaultModel"] == "deepseek-r1"
