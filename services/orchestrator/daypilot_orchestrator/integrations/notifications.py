"""Unified notifications (batch I6).

All providers normalize their activity to one IntegrationEvent shape and land in
one place, grouped by severity (approval / attention / info). Per-integration
delivery rules control how prominently an event surfaces. Notifications are
stored on the existing Event stream (type ``integration.notification``), so the
SSE feed and audit already cover them.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event

NOTIFICATION_EVENT = "integration.notification"
SEVERITIES = ("approval", "attention", "info")

# Delivery modes for per-integration notification rules.
IMMEDIATE = "immediate"
DAILY_SUMMARY = "daily_summary"
IMPORTANT_ONLY = "important_only"
OFF = "off"

# Default rules keyed by (provider, event_type).
DEFAULT_RULES: dict[tuple[str, str], str] = {
    ("slack", "mention.created"): IMMEDIATE,
    ("slack", "message.received"): DAILY_SUMMARY,
    ("github", "connection.error"): IMMEDIATE,
    ("github", "comment.created"): IMMEDIATE,
    ("github", "task.updated"): IMPORTANT_ONLY,
    ("linkedin", "comment.created"): IMMEDIATE,
    ("calendar", "task.updated"): IMPORTANT_ONLY,
}


def normalize(provider: str, event_type: str, title: str, summary: str,
              severity: str = "info", **extra: Any) -> dict[str, Any]:
    """Build the canonical IntegrationEvent payload."""
    return {
        "provider": provider, "type": event_type, "title": title,
        "summary": summary[:280], "severity": severity if severity in SEVERITIES else "info",
        **extra,
    }


def delivery_for(provider: str, event_type: str, rules: dict[tuple[str, str], str] | None = None) -> str:
    return (rules or DEFAULT_RULES).get((provider, event_type), IMMEDIATE)


def record_notification(session: Session, workspace_id: str, event: dict[str, Any]) -> str:
    ev = Event(workspace_id=workspace_id, type=NOTIFICATION_EVENT, payload_json=event)
    session.add(ev)
    session.flush()
    return ev.id


def list_notifications(session: Session, workspace_id: str = "default",
                       severity: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Event).where(Event.workspace_id == workspace_id, Event.type == NOTIFICATION_EVENT)
        .order_by(Event.seq.desc()).limit(limit)
    ).scalars().all()
    out = []
    for e in rows:
        p = e.payload_json or {}
        if severity and p.get("severity") != severity:
            continue
        out.append({
            "id": e.id, "provider": p.get("provider"), "type": p.get("type"),
            "title": p.get("title"), "summary": p.get("summary"),
            "severity": p.get("severity", "info"),
            "occurredAt": e.created_at.isoformat() if e.created_at else None,
            "flagged": p.get("flagged", False),
        })
    return out


def summary(session: Session, workspace_id: str = "default") -> dict[str, int]:
    rows = session.execute(
        select(Event.payload_json).where(
            Event.workspace_id == workspace_id, Event.type == NOTIFICATION_EVENT
        )
    ).scalars().all()
    counts = {s: 0 for s in SEVERITIES}
    for p in rows:
        sev = (p or {}).get("severity", "info")
        if sev in counts:
            counts[sev] += 1
    return counts
