"""Settings → AI providers (v2) — UI contract.

Guards the behaviours that fixed "Couldn't load providers" and made the panel
match what Ollabridge actually offers (local gateway + Cloud): the panel
reconnects instead of dead-ending, names the cause of a load failure, tells a
key-protected local gateway apart from an offline one, lets the person pick a
default model from the gateway's real list, accepts a Cloud API key as well as
an account sign-in, and shows the live routing policy rather than invented
latency figures.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UI = REPO / "packages" / "ui-bridge" / "src"


def _panel() -> str:
    return (UI / "settings" / "AiProvidersPanel.tsx").read_text(encoding="utf-8")


def _client() -> str:
    return (UI / "providersClient.ts").read_text(encoding="utf-8")


def test_panel_reconnects_and_names_the_cause_instead_of_dead_ending() -> None:
    panel = _panel()
    assert "RETRY_DELAYS_MS" in panel and "Retrying automatically" in panel
    assert "Couldn’t load providers" in panel and "Try again" in panel
    assert "providerLoadError" in panel  # API down / proxy misrouted / HTTP error
    # Re-syncs when a provider changes elsewhere or the tab regains focus.
    assert "addEventListener(PROVIDERS_CHANGED_EVENT" in panel and "visibilitychange" in panel
    client = _client()
    assert "gateway_html_response" in client and "gateway_unreachable" in client and "apiBase()" in client
    assert "make run" in client  # the hint tells people how to start the gateway
    # The shared API client tells "nothing answered behind the proxy" apart from
    # "the gateway ran and failed" (an empty text/plain 500 from Vite, or 502-504).
    api = (UI / "apiClient.ts").read_text(encoding="utf-8")
    assert "gateway_unreachable" in api and "502" in api


def test_local_card_distinguishes_ollabridge_gateway_states() -> None:
    panel = _panel()
    for label in ("Key required", "Key rejected", "Reachable · no models", "Offline", "Not detected"):
        assert label in panel
    assert "Open OllaBridge dashboard" in panel and "gatewayDashboardUrl" in panel
    assert "Re-check" in panel and "providersApi.localTest" in panel
    # Default model picker fed by the gateway's live model list.
    assert "providersApi.localModels" in panel and "setDefaultModel" in panel
    assert "/v1/providers/local/models" in _client()


def test_cloud_card_offers_api_key_and_account_sign_in() -> None:
    panel = _panel()
    assert "Sign in with email" in panel and "Use an API key" in panel
    assert "Connect with API key" in panel and "cloudConnectKey" in panel
    assert "Log in on the web" in panel and "Create an account" in panel
    assert "providersApi.cloudModels" in panel  # model picker for cloud too
    client = _client()
    assert "/v1/providers/cloud/connect-key" in client and "cloudKeyErrorText" in client


def test_routing_table_is_live_policy_not_fabricated_measurements() -> None:
    panel = _panel()
    assert "providersApi.routes()" in panel and "latencyBudgetMs" in panel
    data = (UI / "settings" / "settingsData.ts").read_text(encoding="utf-8")
    routes = data.split("PROVIDER_ROUTES")[1].split("PROVIDER_SUMMARY")[0]
    assert "latencyMs:" not in routes and "status:" not in routes
    assert "latencyBudgetMs" in routes


def test_panel_never_stores_provider_state_in_the_browser() -> None:
    panel = _panel()
    assert "localStorage" not in panel and "sessionStorage" not in panel
    # The summary strip explains the active / connected-but-idle situation.
    assert "No active provider" in panel
