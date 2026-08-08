"""Calendar connectors and conflict detection (batch B9).

Read/sync from Google Calendar or Microsoft 365 (mock by default), detect
overlapping events, and propose scheduling changes as approval-gated drafts —
DayPilot never writes a calendar without approval. Conflicts feed Today Context.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, CalendarEvent, Event

_SEED_EVENTS = [
    {"external_id": "ev-1", "title": "Client Alpha review", "start_at": "2026-07-10T09:00:00", "end_at": "2026-07-10T10:00:00", "status": "confirmed"},
    {"external_id": "ev-2", "title": "Deep work: API gateway", "start_at": "2026-07-10T09:30:00", "end_at": "2026-07-10T11:00:00", "status": "confirmed"},
    {"external_id": "ev-3", "title": "Team standup", "start_at": "2026-07-10T11:30:00", "end_at": "2026-07-10T11:45:00", "status": "confirmed"},
]


@dataclass
class Conflict:
    a_id: str
    b_id: str
    a_title: str
    b_title: str


def calendar_provider() -> str:
    return os.getenv("CALENDAR_PROVIDER", "none").lower()


def sync_events(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    """Mock/seed sync — upsert calendar events read-only."""
    out = []
    for seed in _SEED_EVENTS:
        existing = session.execute(
            select(CalendarEvent).where(
                CalendarEvent.workspace_id == workspace_id,
                CalendarEvent.external_id == seed["external_id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            ev = CalendarEvent(
                workspace_id=workspace_id,
                external_id=seed["external_id"],
                title=seed["title"],
                start_at=datetime.fromisoformat(seed["start_at"]),
                end_at=datetime.fromisoformat(seed["end_at"]),
                status=seed["status"],
                source=calendar_provider(),
            )
            session.add(ev)
            session.flush()
            existing = ev
        out.append(_serialize(existing))
    session.flush()
    return out


def _serialize(ev: CalendarEvent) -> dict[str, Any]:
    return {
        "id": ev.id,
        "externalId": ev.external_id,
        "title": ev.title,
        "startAt": ev.start_at.isoformat() if ev.start_at else None,
        "endAt": ev.end_at.isoformat() if ev.end_at else None,
        "status": ev.status,
    }


def list_events(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    """Read the local store. No provider call, no write — this is a read path."""
    rows = session.execute(
        select(CalendarEvent).where(
            CalendarEvent.workspace_id == workspace_id,
        ).order_by(CalendarEvent.start_at.asc())
    ).scalars()
    return [_serialize(r) for r in rows]


def detect_conflicts(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    """Return overlapping event pairs so Command can surface schedule pressure."""
    events = list(
        session.execute(
            select(CalendarEvent).where(
                CalendarEvent.workspace_id == workspace_id,
                CalendarEvent.start_at.isnot(None),
                CalendarEvent.status != "cancelled",
            ).order_by(CalendarEvent.start_at.asc())
        ).scalars()
    )
    conflicts: list[dict[str, Any]] = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.end_at and b.start_at and b.start_at < a.end_at:
                conflicts.append(
                    {"a": a.id, "b": b.id, "aTitle": a.title, "bTitle": b.title}
                )
    return conflicts


def conflicts_on(
    session: Session, workspace_id: str, plan_date: str
) -> list[dict[str, Any]]:
    """Overlapping events on one day.

    The planner needs a day-scoped answer: "no conflicts" across all of history
    is not a claim about today, and today is what the plan is about.
    """
    from datetime import date as _date, time as _time

    try:
        day = _date.fromisoformat(plan_date)
    except ValueError:
        return []
    start = datetime.combine(day, _time.min)
    end = datetime.combine(day, _time.max)
    events = list(
        session.execute(
            select(CalendarEvent).where(
                CalendarEvent.workspace_id == workspace_id,
                CalendarEvent.start_at.isnot(None),
                CalendarEvent.start_at >= start,
                CalendarEvent.start_at <= end,
                CalendarEvent.status != "cancelled",
            ).order_by(CalendarEvent.start_at.asc())
        ).scalars()
    )
    out: list[dict[str, Any]] = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.end_at and b.start_at and b.start_at < a.end_at:
                out.append({"a": a.id, "b": b.id, "aTitle": a.title, "bTitle": b.title})
    return out


def propose_event_draft(
    session: Session, workspace_id: str, title: str, start_at: str, end_at: str
) -> dict[str, Any]:
    """Create a draft calendar event + approval; the write is approval-gated."""
    ev = CalendarEvent(
        workspace_id=workspace_id,
        title=title,
        start_at=datetime.fromisoformat(start_at),
        end_at=datetime.fromisoformat(end_at),
        status="draft",
        source="daypilot",
    )
    session.add(ev)
    session.flush()
    approval = Approval(
        workspace_id=workspace_id,
        action="calendar.create",
        summary=f"Create calendar event '{title}' at {start_at}",
        risk="medium",
        status="pending",
        resource_type="calendar_event",
        resource_id=ev.id,
    )
    session.add(approval)
    session.add(Event(
        workspace_id=workspace_id, type="approval.requested",
        payload_json={"resourceType": "calendar_event", "resourceId": ev.id},
    ))
    session.flush()
    return {"eventId": ev.id, "status": ev.status, "approvalId": approval.id, "approvalStatus": "pending"}
