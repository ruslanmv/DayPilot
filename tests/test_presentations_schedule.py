"""Automatic weekly drafts: correct local times through DST, exactly one draft per period, catch-up
limits, pause, notifications, and nothing ever sent."""

import threading
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import _get_sessionmaker
from app.main import app
from app.presentations import scheduler
from app.routers import presentations as P
from daypilot_knowledge.db.models import PresentationOccurrence, PresentationSeries
from test_presentations import setup_company, story

UTC = timezone.utc


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))


class Inline:
    def __init__(self):
        self.calls = []

    def add_task(self, fn, *args):
        self.calls.append(args)


def make_series(c, h, tz="Europe/Rome"):
    cid, _ = setup_company(c, h, logo=False)
    s = c.post("/v1/presentations/series", json={"companyId": cid, "name": "Weekly", "timezone": tz, "storyline": story()}, headers=h).json()
    return s["id"]


def test_local_times_follow_the_dst_policy():
    sched = {"weekday": 6, "local_time": "02:30"}  # Sunday 02:30, the hour clocks change in Europe
    # Spring gap: 2027-03-28 02:30 does not exist in Rome; it runs at the first valid instant (03:00 CEST = 01:00Z).
    assert scheduler.next_run(sched, "Europe/Rome", datetime(2027, 3, 27, 12, tzinfo=UTC)) == datetime(2027, 3, 28, 1, 0, tzinfo=UTC)
    # Autumn fold: 2026-10-25 02:30 happens twice; the first one (CEST, 00:30Z) is used.
    assert scheduler.next_run(sched, "Europe/Rome", datetime(2026, 10, 24, 12, tzinfo=UTC)) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    # An ordinary week, and strictly after the reference instant.
    monday = {"weekday": 0, "local_time": "08:30"}
    first = scheduler.next_run(monday, "Europe/Rome", datetime(2026, 9, 28, 6, 30, tzinfo=UTC))
    assert first == datetime(2026, 10, 5, 6, 30, tzinfo=UTC)  # 06:30Z itself is not "after"
    assert scheduler.next_run(monday, "America/New_York", datetime(2026, 11, 1, 0, tzinfo=UTC)) == datetime(2026, 11, 2, 13, 30, tzinfo=UTC)
    prev = scheduler.preview(monday, "Europe/Rome", datetime(2026, 10, 1, tzinfo=UTC))
    assert [p["utc"] for p in prev] == ["2026-10-05T06:30:00Z", "2026-10-12T06:30:00Z", "2026-10-19T06:30:00Z"]
    assert prev[0]["period"].startswith("Week 40")
    with pytest.raises(ValueError):
        scheduler.parse_time("8.30")


def test_schedule_endpoint_validates_and_previews():
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    sid = make_series(c, h)
    for bad in ({"enabled": True, "localTime": "25:00"}, {"enabled": True, "weekday": 7}, {"enabled": True, "catchUpHours": 0}):
        assert c.put(f"/v1/presentations/series/{sid}/schedule", json=bad, headers=h).status_code == 422
    r = c.put(f"/v1/presentations/series/{sid}/schedule", json={"enabled": True, "weekday": 0, "localTime": "08:30"}, headers=h).json()["schedule"]
    assert r["enabled"] and r["nextRunAt"] and len(r["upcoming"]) == 3 and "Drafts only" in r["policy"]
    off = c.put(f"/v1/presentations/series/{sid}/schedule", json={"enabled": False}, headers=h).json()["schedule"]
    assert off["enabled"] is False and off["nextRunAt"] is None
    assert c.put(f"/v1/presentations/series/{sid}/schedule", json={"enabled": True}, headers={"X-Workspace-Id": "other"}).status_code == 404


def due(sid, when):
    with _get_sessionmaker()() as s:
        row = s.get(PresentationSeries, sid)
        row.schedule_enabled = True
        row.recipe_json = {**row.recipe_json, "schedule": {"weekday": 0, "local_time": "08:30", "catch_up_hours": 24}}
        row.next_run_at = when.replace(tzinfo=None)
        s.commit()


def occurrences(sid):
    with _get_sessionmaker()() as s:
        return s.query(PresentationOccurrence).filter_by(series_id=sid).count()


def test_a_due_series_prepares_one_draft_and_moves_to_next_week():
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    sid = make_series(c, h)
    due(sid, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    pool = Inline()
    now = datetime(2026, 10, 5, 6, 31, tzinfo=UTC)
    out = [r for r in P.scheduler_tick(now, pool) if r["series"] == sid]
    assert out == [{"series": sid, "status": "prepared", "deck": out[0]["deck"]}] and len(pool.calls) == 1
    assert occurrences(sid) == 1
    assert [r for r in P.scheduler_tick(now, pool) if r["series"] == sid] == []  # not due again
    s = c.get("/v1/presentations/series", headers=h).json()["items"][0]["schedule"]
    assert s["nextRunAt"].startswith("2026-10-12T06:30") and "prepared" in s["lastResult"]
    notes = c.get("/v1/notifications", params={"workspaceId": h["X-Workspace-Id"]}).json()
    items = notes["notifications"]
    assert any("draft ready to review" in str(n) for n in items)
    deck = c.get(f"/v1/presentations/decks/{out[0]['deck']}", headers=h).json()
    assert deck["periodKey"] == "2026-W40-Europe-Rome"


def test_concurrent_workers_fire_a_series_once():
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    sid = make_series(c, h)
    due(sid, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    now = datetime(2026, 10, 5, 6, 35, tzinfo=UTC)
    results = []
    threads = [threading.Thread(target=lambda: results.extend(r for r in P.scheduler_tick(now, Inline()) if r["series"] == sid)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for r in results if r["status"] in ("prepared", "existing")) == 1
    assert occurrences(sid) == 1


def test_late_runs_catch_up_once_and_very_late_ones_are_skipped():
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    sid = make_series(c, h)
    due(sid, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    late = [r for r in P.scheduler_tick(datetime(2026, 10, 5, 20, 0, tzinfo=UTC), Inline()) if r["series"] == sid]
    assert late[0]["status"] == "prepared"  # 13.5 h late, inside the 24 h window
    due(sid, datetime(2026, 10, 12, 6, 30, tzinfo=UTC))
    skipped = [r for r in P.scheduler_tick(datetime(2026, 10, 20, 9, 0, tzinfo=UTC), Inline()) if r["series"] == sid]
    assert skipped[0]["status"] == "skipped" and occurrences(sid) == 1  # no backfill of old weeks
    with _get_sessionmaker()() as s:
        row = s.get(PresentationSeries, sid)
        assert "Skipped" in row.last_result and row.next_run_at > datetime(2026, 10, 20, 9, 0)


def test_paused_and_disabled_series_never_fire():
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    sid = make_series(c, h)
    due(sid, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    c.post(f"/v1/presentations/series/{sid}/pause", headers=h)
    assert [r for r in P.scheduler_tick(datetime(2026, 10, 5, 7, tzinfo=UTC), Inline()) if r["series"] == sid] == []
    c.post(f"/v1/presentations/series/{sid}/pause", headers=h)
    c.put(f"/v1/presentations/series/{sid}/schedule", json={"enabled": False}, headers=h)
    assert [r for r in P.scheduler_tick(datetime(2026, 10, 5, 7, tzinfo=UTC), Inline()) if r["series"] == sid] == []
    assert occurrences(sid) == 0


def test_a_failure_is_recorded_and_does_not_block_other_series(monkeypatch):
    c, h = TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    a, b = make_series(c, h), make_series(c, h)
    due(a, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    due(b, datetime(2026, 10, 5, 6, 30, tzinfo=UTC))
    real = P.prepare_occurrence

    def flaky(session, s, at, background):
        if s.id == a:
            raise RuntimeError("source unavailable")
        return real(session, s, at, background)

    monkeypatch.setattr(P, "prepare_occurrence", flaky)
    out = {r["series"]: r["status"] for r in P.scheduler_tick(datetime(2026, 10, 5, 7, tzinfo=UTC), Inline()) if r["series"] in (a, b)}
    assert out == {a: "failed", b: "prepared"}
    with _get_sessionmaker()() as s:
        assert "source unavailable" in s.get(PresentationSeries, a).last_result
