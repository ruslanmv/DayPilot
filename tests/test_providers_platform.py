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


def test_local_connect_persists_after_successful_probe(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(pp.OllabridgeConnector, "ping",
                        lambda self: (True, 12.0, ["llama3.1", "qwen2.5"]))
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
    monkeypatch.setattr(pp.OllabridgeConnector, "ping", lambda self: (True, 9.0, ["llama3.1"]))
    with session_scope(ENGINE) as s:
        pp.local_connect(s, ws, "http://localhost:11435/v1", None)
    ok = client.patch("/v1/providers/active", json={"workspaceId": ws, "kind": "local"})
    assert ok.status_code == 200 and ok.json()["active"] == "local"


def test_public_view_never_leaks_secrets(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(pp.OllabridgeConnector, "ping", lambda self: (True, 5.0, ["llama3.1"]))
    with session_scope(ENGINE) as s:
        pp.local_connect(s, ws, "http://localhost:11435/v1", "sk-secret-key")
    body = client.get(f"/v1/providers/status?workspaceId={ws}").json()
    blob = str(body)
    assert "sk-secret-key" not in blob and "secret_reference" not in blob and "apiKey" not in blob
