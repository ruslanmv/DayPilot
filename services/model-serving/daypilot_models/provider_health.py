"""Provider health snapshot with graceful degradation (batch B5).

Polls Ollabridge for its model list and round-trip latency. If Ollabridge is
unreachable, DayPilot degrades to the mock backend and surfaces a visible
"degraded" state rather than failing — the app stays usable offline.

No prompts or API keys appear in the returned snapshot or in logs.
"""
from __future__ import annotations

import os

import httpx

from .ollabridge_client import connector_from_env
from .routing import serialize_routes

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_OFFLINE = "offline"


def provider_health(transport: httpx.BaseTransport | None = None) -> dict:
    """Return a credential-free health snapshot for the provider layer."""
    connector = connector_from_env(transport=transport)
    reachable, latency_ms, models = connector.ping()

    if reachable and models:
        status = STATUS_HEALTHY
    elif reachable:
        # Reachable but advertising no models — usable but degraded.
        status = STATUS_DEGRADED
    else:
        status = STATUS_OFFLINE

    fallback_active = status != STATUS_HEALTHY
    return {
        "provider": "ollabridge",
        # URL only (never the key) so operators can see where routing points.
        "url": os.getenv("OLLABRIDGE_URL", "http://localhost:8100/v1"),
        "status": status,
        "latencyMs": latency_ms,
        "models": models,
        "defaultModel": connector.model,
        "fallbackBackend": "mock" if fallback_active else None,
        "degraded": fallback_active,
        "routes": serialize_routes(),
    }
