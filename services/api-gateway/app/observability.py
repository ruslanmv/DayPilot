"""Request observability for the gateway (batch B14).

Adds a request ID to every request/response, emits one structured JSON log line
per request (method, path, status, duration, request + workspace IDs), and
records a Prometheus latency histogram by route. Secrets are redacted from logs.
This is the span boundary an OpenTelemetry exporter hooks into in production.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:  # keep the gateway importable if the orchestrator isn't on the path
    from daypilot_orchestrator.security.secrets import redact
except Exception:  # pragma: no cover
    def redact(text: str) -> str:
        return text

logger = logging.getLogger("daypilot.gateway")

REQUEST_LATENCY = Histogram(
    "daypilot_gateway_request_seconds", "Gateway request latency", ["method", "route", "status"]
)
REQUEST_ERRORS = Counter("daypilot_gateway_request_errors_total", "Gateway request errors", ["route"])


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        workspace_id = request.query_params.get("workspaceId", "default")
        start = time.perf_counter()
        status = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            REQUEST_ERRORS.labels(route=request.url.path).inc()
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            matched = request.scope.get("route")
            route = matched.path if matched is not None else request.url.path
            REQUEST_LATENCY.labels(request.method, route, str(status)).observe(duration_ms / 1000)
            logger.info(
                redact(json.dumps({
                    "level": "info" if status < 500 else "error",
                    "msg": "request",
                    "requestId": request_id,
                    "workspaceId": workspace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "durationMs": duration_ms,
                }, separators=(",", ":")))
            )


def install_observability(app) -> None:
    app.add_middleware(ObservabilityMiddleware)
