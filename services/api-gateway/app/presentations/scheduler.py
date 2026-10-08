"""Opt-in automatic weekly drafts.

A series with a schedule gets a ``next_run_at`` instant computed in its own timezone. A worker
claims a due series by moving ``next_run_at`` forward with a compare-and-swap, so two workers can
never both fire it, then prepares the period's draft through the same idempotent path as the
"Prepare this week" button. Drafts only: nothing is shared or sent. The owner gets an in-app
notification. Runs missed while the server was down are caught up once (latest period only) within
the catch-up window; older ones are skipped and recorded.

Daylight-saving policy (shown before activation): a local time that does not exist (spring gap)
moves forward to the first valid instant; a local time that happens twice (autumn fold) uses the
first occurrence.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from daypilot_knowledge.db.models import PresentationSeries

from . import weekly

log = logging.getLogger("daypilot.presentations.scheduler")
TICK_SECONDS = 60


def enabled() -> bool:
    return os.getenv("DAYPILOT_PRESENTATIONS_SCHEDULER", "false").lower() == "true"


def _utc(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _instant(day: date, at: time, tz_name: str) -> datetime:
    """Local wall time → UTC with the documented gap/fold policy."""
    tz = weekly.zone(tz_name)
    local = datetime.combine(day, at, tzinfo=tz).replace(fold=0)  # fold=0: first of a repeated hour
    utc = local.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) == local.replace(tzinfo=None):
        return utc
    # The wall time is inside a gap: the first valid instant is where the clock lands after it.
    probe = datetime.combine(day, at, tzinfo=tz) - timedelta(hours=3)
    probe = probe.astimezone(timezone.utc)
    while probe.astimezone(tz).replace(tzinfo=None) < local.replace(tzinfo=None):
        probe += timedelta(minutes=1)
    return probe


def parse_time(value: str) -> time:
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError) as exc:
        raise ValueError("time must be HH:MM (24-hour)") from exc


def next_run(schedule: dict[str, Any], tz_name: str, after: datetime) -> datetime:
    """The first scheduled instant strictly after ``after`` (UTC)."""
    weekday, at = int(schedule["weekday"]), parse_time(schedule["local_time"])
    after = _utc(after)
    local_day = after.astimezone(weekly.zone(tz_name)).date() - timedelta(days=1)
    for k in range(0, 16):
        day = local_day + timedelta(days=k)
        if day.weekday() != weekday:
            continue
        candidate = _instant(day, at, tz_name)
        if candidate > after:
            return candidate
    raise RuntimeError("no next run found")  # unreachable for a valid weekday


def preview(schedule: dict[str, Any], tz_name: str, after: datetime, n: int = 3) -> list[dict[str, str]]:
    out, cursor = [], _utc(after)
    tz = weekly.zone(tz_name)
    for _ in range(n):
        cursor = next_run(schedule, tz_name, cursor)
        p = weekly.period("previous_full_week", tz_name, 0, cursor)
        out.append({"utc": cursor.isoformat().replace("+00:00", "Z"), "local": cursor.astimezone(tz).strftime("%a %d %b %Y %H:%M %Z"), "period": p["label"]})
    return out


def tick(session: Session, now: datetime, prepare: Callable[[Session, PresentationSeries, datetime], dict[str, Any]], notify: Callable[[Session, PresentationSeries, str, str], None]) -> list[dict[str, Any]]:
    """Fire every due series once. Safe to run on several workers at the same time."""
    now = _utc(now)
    naive_now = now.replace(tzinfo=None)
    due = session.execute(
        select(PresentationSeries).where(
            PresentationSeries.schedule_enabled.is_(True), PresentationSeries.paused.is_(False),
            PresentationSeries.next_run_at.is_not(None), PresentationSeries.next_run_at <= naive_now,
        )
    ).scalars().all()
    results = []
    for s in due:
        planned = _utc(s.next_run_at)
        schedule = s.recipe_json.get("schedule") or {}
        following = next_run(schedule, s.recipe_json["timezone"], now).replace(tzinfo=None)
        won = session.execute(
            update(PresentationSeries)
            .where(PresentationSeries.id == s.id, PresentationSeries.next_run_at == s.next_run_at)
            .values(next_run_at=following, last_fired_at=naive_now)
        ).rowcount == 1
        session.commit()
        if not won:
            continue  # another worker took it
        session.refresh(s)
        late = now - planned
        catch_up = timedelta(hours=int(schedule.get("catch_up_hours", 24)))
        if late > catch_up:
            message = f"Skipped the run planned for {planned.isoformat()} ({int(late.total_seconds() // 3600)} h late, beyond the {catch_up.total_seconds() // 3600:.0f} h catch-up window)."
            s.last_result = message[:300]
            notify(session, s, "Weekly draft skipped", message)
            session.commit()
            results.append({"series": s.id, "status": "skipped"})
            continue
        try:
            out = prepare(session, s, now)
            message = f"Draft for {out['period']['label']} {'prepared' if out['created'] else 'already existed'}."
            s.last_result = message[:300]
            notify(session, s, f"{s.name}: draft ready to review", message)
            session.commit()
            results.append({"series": s.id, "status": "prepared" if out["created"] else "existing", "deck": out["deck"]["id"]})
        except Exception as exc:  # noqa: BLE001 - one bad series must not stop the others
            session.rollback()
            s = session.get(PresentationSeries, s.id)
            s.last_result = f"Failed: {str(exc)[:250]}"
            notify(session, s, f"{s.name}: draft could not be prepared", s.last_result)
            session.commit()
            results.append({"series": s.id, "status": "failed"})
    return results


class Pool:
    """``add_task`` for builds started by the scheduler (outside any request)."""

    def __init__(self, workers: int = 2) -> None:
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dp-deck")

    def add_task(self, fn: Callable[..., Any], *args: Any) -> None:
        self.executor.submit(fn, *args)


_stop = threading.Event()
_thread: threading.Thread | None = None


def start(run_tick: Callable[[], None]) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def loop() -> None:
        while not _stop.wait(TICK_SECONDS):
            try:
                run_tick()
            except Exception:  # noqa: BLE001
                log.exception("presentation scheduler tick failed")

    _thread = threading.Thread(target=loop, name="dp-presentations-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
