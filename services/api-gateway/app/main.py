from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

try:
    from daypilot_mcp_host.homepilot_bridge import preview_hpersona_bytes
except Exception:  # pragma: no cover - import path differs during early scaffolding
    preview_hpersona_bytes = None

from .routers import (
    agents,
    approvals,
    assistant,
    auth_identity,
    calendar,
    catalog,
    chat,
    coding,
    design,
    documents,
    email,
    events,
    homepilot,
    integrations,
    integrations_mcp,
    jobs,
    knowledge,
    notifications,
    plan,
    planner,
    profile,
    projects,
    providers,
    tasks,
)

from contextlib import asynccontextmanager

from .db_bootstrap import ensure_schema
from .observability import install_observability

REQUESTS = Counter("daypilot_api_gateway_requests_total", "Gateway requests", ["route"])


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Auto-apply migrations on startup so a fresh install never hits
    # 'no such table'. Opt out with DAYPILOT_AUTO_MIGRATE=0. This must never
    # crash startup — ensure_schema swallows everything, and we guard again here.
    try:
        ensure_schema()
    except BaseException:  # noqa: BLE001 - a schema hiccup can't take down the server
        pass
    yield


app = FastAPI(title="DayPilot API Gateway", version="0.3.0", lifespan=_lifespan)
install_observability(app)

for _router in (
    # HomePilot first so its specific /v1/agents/profiles* routes are matched
    # before the agents router's /v1/agents/{run_id} catch-all.
    homepilot.router,
    tasks.router,
    projects.router,
    agents.router,
    documents.router,
    approvals.router,
    plan.router,
    events.router,
    providers.router,
    coding.router,
    design.router,
    email.router,
    calendar.router,
    jobs.router,
    integrations.router,
    integrations_mcp.router,
    notifications.router,
    catalog.router,
    planner.router,
    chat.router,
    auth_identity.router,
    assistant.router,
    knowledge.router,
    profile.router,
    profile.onboarding_router,
):
    app.include_router(_router)

SERVICE_MAP = {
    "orchestrator": "http://orchestrator:8002",
    "mcp-host": "http://mcp-host:8003",
    "knowledge-service": "http://knowledge-service:8004",
    "model-serving": "http://model-serving:8005",
    "voice-gateway": "http://voice-gateway:8006",
    "observability": "http://observability:8010",
}


@app.get("/health")
def health() -> dict:
    REQUESTS.labels(route="health").inc()
    return {
        "ok": True,
        "service": "daypilot-api-gateway",
        "version": "0.3.0",
        "homepilot_imports": preview_hpersona_bytes is not None,
        "services": SERVICE_MAP,
    }


@app.get("/v1/operator/briefing")
def daily_briefing() -> dict:
    REQUESTS.labels(route="briefing").inc()
    return {
        "status": "ready_for_connectors",
        "briefing": [
            "Review imported HomePilot personas and policy state.",
            "Check orchestrator approval queue before write-capable tool execution.",
            "Verify knowledge-service migrations before persistent indexing.",
            "Confirm model-serving backend is mock, Ollama, or vLLM for this environment.",
        ],
    }


@app.post("/v1/homepilot/personas/preview")
async def preview_homepilot_persona(file: UploadFile = File(...)) -> dict:
    REQUESTS.labels(route="hpersona-preview").inc()
    if preview_hpersona_bytes is None:
        raise HTTPException(status_code=503, detail="HomePilot bridge not installed on import path")
    data = await file.read()
    return preview_hpersona_bytes(data)


@app.get("/v1/personas")
def list_personas() -> dict:
    REQUESTS.labels(route="personas").inc()
    base = Path("local_data/installed_personas")
    personas = []
    if base.exists():
        for persona_json in base.glob("*/persona.json"):
            personas.append(persona_json.read_text(encoding="utf-8"))
    return {"status": "ok", "count": len(personas), "items": personas}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Single-origin production serving: strip `/api` and serve the built SPA when a
# web build is present. Added last so every API route is registered first and
# always wins over the static mount. No-op for the dev flow and tests.
from .webserve import mount_web  # noqa: E402

mount_web(app)
