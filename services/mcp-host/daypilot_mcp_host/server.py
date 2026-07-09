from __future__ import annotations

from fastapi import FastAPI, File, UploadFile
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

from daypilot_mcp_host.homepilot_bridge import preview_hpersona_bytes
from daypilot_mcp_host.registry import DEFAULT_TOOLS

PREVIEWS = Counter("daypilot_mcp_hpersona_previews_total", "HomePilot .hpersona previews")

app = FastAPI(title="DayPilot MCP Host", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "daypilot-mcp-host", "tools": len(DEFAULT_TOOLS)}


@app.get("/v1/tools")
def tools() -> dict:
    return {"items": [tool.__dict__ for tool in DEFAULT_TOOLS]}


@app.post("/v1/homepilot/personas/preview")
async def preview(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    PREVIEWS.inc()
    return preview_hpersona_bytes(data)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
