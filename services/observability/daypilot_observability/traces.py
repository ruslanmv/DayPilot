from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from daypilot_observability.logging_config import configure_logging
from daypilot_observability.metrics import SERVICE_HEALTH_CHECKS, TRACE_EVENTS

configure_logging(os.getenv("DAYPILOT_LOG_LEVEL", "INFO"))

_TRACE_BUFFER: list[dict[str, Any]] = []


class TraceEvent(BaseModel):
    service: str = "unknown"
    event_type: str = Field(default="generic")
    payload: dict[str, Any] = Field(default_factory=dict)


def record_trace(event: dict[str, Any]) -> dict[str, Any]:
    service = event.get("service", "unknown")
    event_type = event.get("event_type", "generic")
    envelope = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": service,
        "event_type": event_type,
        "payload": event.get("payload", event),
    }
    _TRACE_BUFFER.append(envelope)
    del _TRACE_BUFFER[:-500]
    TRACE_EVENTS.labels(service=service, event_type=event_type).inc()
    return {"status": "recorded", "event": envelope}


app = FastAPI(title="DayPilot Observability", version="0.2.0")


@app.get("/health")
def health() -> dict[str, Any]:
    SERVICE_HEALTH_CHECKS.labels(service="observability").inc()
    return {"ok": True, "service": "daypilot-observability", "buffered_events": len(_TRACE_BUFFER)}


@app.post("/v1/traces")
def trace(event: TraceEvent) -> dict[str, Any]:
    return record_trace(event.model_dump())


@app.get("/v1/traces")
def list_traces(limit: int = 50) -> dict[str, Any]:
    return {"items": _TRACE_BUFFER[-limit:], "count": min(limit, len(_TRACE_BUFFER))}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
