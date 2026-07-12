from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from daypilot_models.provider_health import provider_health
from daypilot_models.routing import route_for_role, serialize_routes

router = APIRouter(prefix="/v1/providers", tags=["providers"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Ollabridge provider health: status, latency, models, routes, fallback."""
    return provider_health()


@router.get("/routes")
def routes() -> dict[str, Any]:
    return {"routes": serialize_routes()}


@router.get("/route/{role}")
def route(role: str) -> dict[str, Any]:
    policy = route_for_role(role)
    return {
        "role": policy.role,
        "model": policy.preferred_model,
        "tier": policy.tier,
        "latencyBudgetMs": policy.latency_budget_ms,
        "fallback": list(policy.fallback),
    }
