from __future__ import annotations

from prometheus_client import Counter, Histogram

SERVICE_HEALTH_CHECKS = Counter(
    "daypilot_service_health_checks_total",
    "Health checks observed by service",
    ["service"],
)
TRACE_EVENTS = Counter(
    "daypilot_trace_events_total",
    "Trace events recorded",
    ["service", "event_type"],
)
REQUEST_LATENCY = Histogram(
    "daypilot_request_latency_seconds",
    "Observed request latency by service and operation",
    ["service", "operation"],
)
