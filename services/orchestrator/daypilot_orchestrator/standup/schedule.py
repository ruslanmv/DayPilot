"""When the standup runs, in the user's own timezone.

Everything here works in the workflow's local timezone and converts to naive
UTC only at the boundary, because the whole point is that "18:00" means 18:00
to the person reading it — including on the two days a year when the clocks
move and a fixed UTC offset would drift the review an hour into their evening.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Monday–Friday, ISO weekday numbers.
DEFAULT_WORKING_DAYS = [1, 2, 3, 4, 5]

#: How long after the reminder time we keep looking for the thread before
#: giving up for the day. Long enough to survive a late Slack workflow, short
#: enough that the update is still same-morning news.
THREAD_SEARCH_MINUTES = 180


class ScheduleError(ValueError):
    """A workflow's schedule fields cannot be interpreted."""


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduleError(f"unknown timezone {name!r}") from exc


def parse_hhmm(value: str) -> time:
    try:
        hour, minute = (int(part) for part in str(value).split(":", 1))
        return time(hour=hour, minute=minute)
    except (TypeError, ValueError) as exc:
        raise ScheduleError(f"expected HH:MM, got {value!r}") from exc


def working_days(raw: list[int] | None) -> list[int]:
    days = sorted({int(d) for d in (raw or []) if 1 <= int(d) <= 7})
    return days or list(DEFAULT_WORKING_DAYS)


def is_working_day(day: date, days: list[int] | None) -> bool:
    return day.isoweekday() in working_days(days)


def previous_working_day(day: date, days: list[int] | None) -> date:
    """The workday before ``day``.

    Monday's standup reports on Friday, not on Sunday. Walking backwards over
    the configured days is what makes that true for a Tue–Sat week as well,
    rather than special-casing weekends.
    """
    allowed = working_days(days)
    cursor = day - timedelta(days=1)
    for _ in range(14):
        if cursor.isoweekday() in allowed:
            return cursor
        cursor -= timedelta(days=1)
    return day - timedelta(days=1)


def next_working_day(day: date, days: list[int] | None) -> date:
    allowed = working_days(days)
    cursor = day + timedelta(days=1)
    for _ in range(14):
        if cursor.isoweekday() in allowed:
            return cursor
        cursor += timedelta(days=1)
    return day + timedelta(days=1)


def to_utc(local_dt: datetime, tz: ZoneInfo) -> datetime:
    """A naive-UTC timestamp for a local wall-clock time.

    Naive because that is what the ``jobs`` table and the rest of DayPilot
    store; the conversion happens here so no caller has to remember it.
    """
    return local_dt.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def local_now(tz: ZoneInfo, now_utc: datetime | None = None) -> datetime:
    base = (now_utc or datetime.utcnow()).replace(tzinfo=ZoneInfo("UTC"))
    return base.astimezone(tz).replace(tzinfo=None)


@dataclass(frozen=True)
class Occurrence:
    """One scheduled moment, in both clocks."""

    local: datetime
    utc: datetime
    day: date


def next_occurrence(
    *,
    timezone_name: str,
    at: str,
    days: list[int] | None,
    now_utc: datetime | None = None,
    inclusive: bool = False,
) -> Occurrence:
    """The next time ``at`` happens on a working day.

    ``inclusive`` returns *now* when it lands exactly on the scheduled minute,
    which is what a job that just fired needs so it can decide whether it is
    the run it was scheduled for.
    """
    tz = zone(timezone_name)
    wall = parse_hhmm(at)
    current = local_now(tz, now_utc)

    candidate = datetime.combine(current.date(), wall)
    later = candidate > current if not inclusive else candidate >= current
    if not (later and is_working_day(candidate.date(), days)):
        cursor = current.date()
        for _ in range(14):
            cursor = next_working_day(cursor, days)
            candidate = datetime.combine(cursor, wall)
            if candidate > current:
                break
    return Occurrence(local=candidate, utc=to_utc(candidate, tz), day=candidate.date())


def reporting_window(
    *,
    timezone_name: str,
    reporting_day: date,
    days: list[int] | None,
) -> tuple[datetime, datetime]:
    """The UTC window whose activity belongs to ``reporting_day``.

    It opens at the end of the *previous working day's* review, not at
    midnight: work done at 19:30 on Tuesday belongs in Wednesday's standup, and
    a midnight boundary would silently drop it. On a Monday the window
    therefore reaches back across the weekend to Friday evening.
    """
    tz = zone(timezone_name)
    previous = previous_working_day(reporting_day, days)
    start_local = datetime.combine(previous, time(18, 0))
    end_local = datetime.combine(reporting_day, time(23, 59, 59))
    return to_utc(start_local, tz), to_utc(end_local, tz)


def target_standup_day(
    *,
    reporting_day: date,
    delivery_mode: str,
    days: list[int] | None,
) -> date:
    """Which standup thread this reporting day's work is posted into."""
    if delivery_mode == "same_day":
        return reporting_day
    return next_working_day(reporting_day, days)


def thread_search_window(
    *,
    timezone_name: str,
    standup_day: date,
    reminder_time: str,
    minutes: int = THREAD_SEARCH_MINUTES,
) -> tuple[datetime, datetime]:
    """When to look for that morning's reminder message.

    Bounded on both sides: a message from 30 minutes before the reminder time
    is plausibly the reminder posted early, one from six hours later is
    somebody else's thread.
    """
    tz = zone(timezone_name)
    wall = parse_hhmm(reminder_time)
    opens = datetime.combine(standup_day, wall) - timedelta(minutes=30)
    closes = datetime.combine(standup_day, wall) + timedelta(minutes=minutes)
    return to_utc(opens, tz), to_utc(closes, tz)
