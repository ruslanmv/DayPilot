"""Tests for the Ollabridge provider layer (batch B5).

Uses httpx MockTransport so no network is required and the request contract is
asserted precisely, including graceful degradation and no-secret-leakage.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_models.ollabridge_client import OllabridgeConnector
from daypilot_models.provider_health import provider_health
from daypilot_models.routing import route_for_role, serialize_routes

client = TestClient(app)


def _chat_transport() -> httpx.MockTransport:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "hello from ollabridge"}}],
                    "usage": {"total_tokens": 12},
                },
            )
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama3.1"}, {"id": "mixtral"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    transport._captured = captured  # type: ignore[attr-defined]
    return transport


def test_generate_posts_openai_compatible_chat():
    transport = _chat_transport()
    connector = OllabridgeConnector(
        base_url="http://ollabridge.test/v1".removesuffix("/v1"),
        api_key="secret-key",
        model="llama3.1",
        transport=transport,
    )
    result = connector.generate("Plan my day", task="planner")
    assert result["backend"] == "ollabridge"
    assert result["text"] == "hello from ollabridge"
    assert result["model"] == "llama3.1"
    captured = transport._captured  # type: ignore[attr-defined]
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["auth"] == "Bearer secret-key"


def test_connector_from_env_defaults_to_local(monkeypatch):
    for var in ("OLLABRIDGE_MODE", "OLLABRIDGE_URL", "OLLABRIDGE_BASE_URL", "OLLABRIDGE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from daypilot_models.ollabridge_client import connector_from_env

    conn = connector_from_env()
    assert conn.mode == "local"
    assert conn.base_url == "http://localhost:11435"  # local gateway, /v1 stripped


def test_connector_from_env_pairs_with_cloud(monkeypatch):
    monkeypatch.setenv("OLLABRIDGE_MODE", "cloud")
    monkeypatch.delenv("OLLABRIDGE_URL", raising=False)
    monkeypatch.delenv("OLLABRIDGE_BASE_URL", raising=False)
    monkeypatch.setenv("OLLABRIDGE_API_KEY", "ob_live_secret")
    from daypilot_models.ollabridge_client import connector_from_env

    conn = connector_from_env()
    assert conn.mode == "cloud"
    assert conn.base_url == "https://ruslanmv-ollabridge-cloud.hf.space"
    assert conn.api_key == "ob_live_secret"


def test_explicit_url_overrides_mode_default(monkeypatch):
    monkeypatch.setenv("OLLABRIDGE_MODE", "cloud")
    monkeypatch.setenv("OLLABRIDGE_BASE_URL", "https://my-node.example.com/v1")
    from daypilot_models.ollabridge_client import connector_from_env

    conn = connector_from_env()
    assert conn.base_url == "https://my-node.example.com"
    assert conn.mode == "cloud"


def test_cloud_device_pairing_handshake():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/device/start"):
            return httpx.Response(200, json={
                "user_code": "ABCD-1234",
                "device_code": "dev-xyz",
                "verification_uri": "https://ollabridge.cloud/pair",
                "interval": 5,
            })
        if request.url.path.endswith("/device/poll"):
            return httpx.Response(200, json={"status": "approved", "api_key": "ob_live_paired"})
        return httpx.Response(404)

    conn = OllabridgeConnector(
        base_url="https://ollabridge.cloud", mode="cloud",
        transport=httpx.MockTransport(handler),
    )
    session = conn.start_pairing()
    assert session["user_code"] == "ABCD-1234"
    approved = conn.poll_pairing(session["device_code"])
    assert approved["status"] == "approved"
    assert approved["api_key"] == "ob_live_paired"


def test_normalize_gateway_root_strips_openai_suffixes():
    from daypilot_models.ollabridge_client import normalize_gateway_root

    assert normalize_gateway_root("http://localhost:11435/v1") == "http://localhost:11435"
    assert normalize_gateway_root("http://localhost:11435/v1/") == "http://localhost:11435"
    assert normalize_gateway_root("https://x.hf.space/ollama/v1") == "https://x.hf.space"
    assert normalize_gateway_root("http://localhost:11435") == "http://localhost:11435"


def test_no_double_v1_when_base_already_includes_v1():
    """Regression: the stored base is the OpenAI base (…/v1). The connector must
    still probe /v1/models — not /v1/v1/models — which was the 404 that made a
    running local gateway look offline."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["xapikey"] = request.headers.get("x-api-key")
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama3"}]})
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    conn = OllabridgeConnector(
        base_url="http://localhost:11435/v1",  # OpenAI base, as DayPilot stores it
        api_key="sk-ollabridge-abc",
        transport=httpx.MockTransport(handler),
    )
    assert conn.base_url == "http://localhost:11435"  # normalized to the root
    assert conn.list_models() == ["llama3"]
    assert captured["path"] == "/v1/models"  # NOT /v1/v1/models
    # Local mode also presents the key as X-API-Key per the Ollabridge contract.
    assert captured["xapikey"] == "sk-ollabridge-abc"
    assert conn.health() is True  # /health lives at the root


def test_list_models_and_ping():
    connector = OllabridgeConnector(base_url="http://ollabridge.test", transport=_chat_transport())
    assert connector.list_models() == ["llama3.1", "mixtral"]
    reachable, latency, models = connector.ping()
    assert reachable is True
    assert latency is not None and latency >= 0
    assert "mixtral" in models


def test_ping_never_raises_when_offline():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    connector = OllabridgeConnector(base_url="http://down.test", transport=httpx.MockTransport(boom))
    reachable, latency, models = connector.ping()
    assert reachable is False
    assert latency is None
    assert models == []


def test_provider_health_degrades_gracefully_offline():
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    snapshot = provider_health(transport=httpx.MockTransport(boom))
    assert snapshot["status"] == "offline"
    assert snapshot["degraded"] is True
    assert snapshot["fallbackBackend"] == "mock"
    # A credential must never appear in the health snapshot.
    assert "secret" not in str(snapshot).lower()
    assert "api_key" not in snapshot and "apiKey" not in snapshot


def test_provider_health_healthy_when_models_present():
    snapshot = provider_health(transport=_chat_transport())
    assert snapshot["status"] == "healthy"
    assert snapshot["degraded"] is False
    assert "llama3.1" in snapshot["models"]


@pytest.mark.parametrize(
    "role,tier",
    [("email_sentinel", "local"), ("document_assistant", "hybrid"), ("coding-agent", "hybrid")],
)
def test_routing_policy_tiers(role, tier):
    assert route_for_role(role).tier == tier


def test_unknown_role_falls_back_to_default():
    assert route_for_role("mystery").role == "planner"


def test_serialize_routes_shape():
    routes = serialize_routes()
    assert routes and all({"role", "model", "tier", "fallback"} <= set(r) for r in routes)


# --- Gateway endpoints ------------------------------------------------------

def test_gateway_providers_routes_endpoint():
    body = client.get("/v1/providers/routes").json()
    assert any(r["role"] == "email_sentinel" for r in body["routes"])


def test_gateway_providers_health_endpoint():
    body = client.get("/v1/providers/health").json()
    assert body["provider"] == "ollabridge"
    assert body["status"] in {"healthy", "degraded", "offline"}
    assert "routes" in body
