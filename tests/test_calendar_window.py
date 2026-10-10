"""`GET /v1/calendar/events` with an optional window.

The Echo display asks for a week of events, not the whole calendar: the payload
and the pairwise conflict check stay the size of the window on a small device.
Without `start`/`end` the endpoint answers exactly as before.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import CalendarEvent, create_engine_from_settings, session_scope

client = TestClient(app)
ENGINE = create_engine_from_settings()
WS = "ws_calendar_window"


@pytest.fixture()
def events():
    rows = [
        ("Old offsite", "2026-07-01T10:00:00", "2026-07-01T17:00:00", "confirmed"),
        ("Sync", "2026-10-10T11:00:00", "2026-10-10T11:30:00", "confirmed"),
        ("Check-in", "2026-10-10T11:15:00", "2026-10-10T11:45:00", "confirmed"),
        ("Cancelled demo", "2026-10-10T11:00:00", "2026-10-10T12:00:00", "cancelled"),
        ("Trip", "2026-10-08T09:00:00", "2026-10-11T18:00:00", "confirmed"),
        ("Board prep", "2026-10-15T10:00:00", "2026-10-15T12:00:00", "confirmed"),
    ]
    with session_scope(ENGINE) as s:
        for row in s.query(CalendarEvent).filter_by(workspace_id=WS).all():
            s.delete(row)
        for title, start, end, status in rows:
            s.add(CalendarEvent(workspace_id=WS, title=title, start_at=datetime.fromisoformat(start),
                                end_at=datetime.fromisoformat(end), status=status))
    yield
    with session_scope(ENGINE) as s:
        for row in s.query(CalendarEvent).filter_by(workspace_id=WS).all():
            s.delete(row)


def _titles(body):
    return sorted(e["title"] for e in body["items"])


def test_without_a_window_every_event_is_returned_as_before(events):
    body = client.get("/v1/calendar/events", params={"workspaceId": WS}).json()
    assert len(body["items"]) == 6
    assert "provider" in body


def test_a_window_returns_overlapping_events_only(events):
    body = client.get("/v1/calendar/events", params={
        "workspaceId": WS, "start": "2026-10-10T00:00:00Z", "end": "2026-10-11T00:00:00Z",
    }).json()
    # The trip started before the window and is still running inside it.
    assert _titles(body) == ["Cancelled demo", "Check-in", "Sync", "Trip"]


def test_conflicts_are_computed_among_the_window_and_ignore_cancelled_events(events):
    body = client.get("/v1/calendar/events", params={
        "workspaceId": WS, "start": "2026-10-10T00:00:00+00:00", "end": "2026-10-11T00:00:00+00:00",
    }).json()
    pairs = sorted(tuple(sorted((c["aTitle"], c["bTitle"]))) for c in body["conflicts"])
    assert ("Check-in", "Sync") in pairs
    assert all("Cancelled demo" not in p for p in pairs)


def test_an_open_ended_window_works_from_either_side(events):
    after = client.get("/v1/calendar/events", params={"workspaceId": WS, "start": "2026-10-12T00:00:00"}).json()
    assert _titles(after) == ["Board prep"]
    before = client.get("/v1/calendar/events", params={"workspaceId": WS, "end": "2026-08-01T00:00:00"}).json()
    assert _titles(before) == ["Old offsite"]


def test_a_malformed_bound_is_refused(events):
    res = client.get("/v1/calendar/events", params={"workspaceId": WS, "start": "next tuesday"})
    assert res.status_code == 422
