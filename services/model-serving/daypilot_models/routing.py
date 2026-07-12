"""Per-agent-role model routing policy (batch B5).

Each DayPilot agent role has a preferred model, a latency budget, a privacy tier
(local-first by default so documents and personas never leave the device
unless explicitly allowed), and an ordered fallback chain. Ollabridge executes
the request against whichever compute matches the tier.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoutePolicy:
    role: str
    preferred_model: str
    tier: str  # local | hybrid | cloud
    latency_budget_ms: int
    fallback: tuple[str, ...] = field(default_factory=tuple)


# Local-first defaults: sensitive roles (email, documents) stay on-device.
AGENT_ROUTES: dict[str, RoutePolicy] = {
    "scheduler": RoutePolicy("scheduler", "llama3.1", "local", 800, ("mistral",)),
    "email_sentinel": RoutePolicy("email_sentinel", "llama3.1", "local", 1200, ("mistral",)),
    "document_assistant": RoutePolicy("document_assistant", "mixtral", "hybrid", 2500, ("llama3.1",)),
    "project_analyst": RoutePolicy("project_analyst", "mixtral", "hybrid", 2500, ("llama3.1",)),
    "coding_agent": RoutePolicy("coding_agent", "deepseek-coder", "hybrid", 4000, ("qwen2.5-coder", "llama3.1")),
    "planner": RoutePolicy("planner", "llama3.1", "local", 1500, ("mixtral",)),
}

DEFAULT_ROLE = "planner"


def route_for_role(role: str) -> RoutePolicy:
    return AGENT_ROUTES.get(role.lower().replace("-", "_"), AGENT_ROUTES[DEFAULT_ROLE])


def serialize_routes() -> list[dict]:
    return [
        {
            "role": p.role,
            "model": p.preferred_model,
            "tier": p.tier,
            "latencyBudgetMs": p.latency_budget_ms,
            "fallback": list(p.fallback),
        }
        for p in AGENT_ROUTES.values()
    ]
