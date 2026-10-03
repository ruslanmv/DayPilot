"""Weekly series: reporting periods in the series' own timezone, and carry-forward without stale facts."""

from __future__ import annotations

import copy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RULES = ("previous_full_week", "current_week")


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {name!r}") from exc


def _local_midnight_utc(day: date, tz: ZoneInfo) -> datetime:
    """Local midnight as a UTC instant. A nonexistent midnight (DST gap) moves forward to the first
    valid instant; a repeated one uses the first occurrence (fold=0)."""
    local = datetime.combine(day, time(0, 0), tzinfo=tz)
    utc = local.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) != local.replace(tzinfo=None):  # fell into a gap
        utc = datetime.combine(day, time(1, 0), tzinfo=tz).astimezone(timezone.utc).replace(minute=0)
    return utc


def period(rule: str, tz_name: str, week_starts_on: int = 0, at: datetime | None = None) -> dict[str, str]:
    """Start-inclusive, end-exclusive reporting window as UTC ISO strings, plus a stable key and label."""
    if rule not in RULES:
        raise ValueError(f"reporting rule must be one of {', '.join(RULES)}")
    if not 0 <= week_starts_on <= 6:
        raise ValueError("week_starts_on is 0 (Monday) to 6 (Sunday)")
    tz = zone(tz_name)
    at = at or datetime.now(timezone.utc)
    today = at.astimezone(tz).date()
    start_this = today - timedelta(days=(today.weekday() - week_starts_on) % 7)
    start = start_this - timedelta(days=7) if rule == "previous_full_week" else start_this
    end = start + timedelta(days=7)
    iso = start.isocalendar()
    key = (f"{iso.year}-W{iso.week:02d}" if week_starts_on == 0 else f"{start.isoformat()}-7d") + "-" + tz_name.replace("/", "-")
    last = end - timedelta(days=1)
    label = f"Week {iso.week} · {start.strftime('%d %b')} – {last.strftime('%d %b %Y')}" if week_starts_on == 0 else f"{start.strftime('%d %b')} – {last.strftime('%d %b %Y')}"
    return {
        "key": key[:60],
        "label": label,
        "start": _local_midnight_utc(start, tz).isoformat().replace("+00:00", "Z"),
        "end_exclusive": _local_midnight_utc(end, tz).isoformat().replace("+00:00", "Z"),
        "timezone": tz_name,
    }


def carry_forward(storyline: dict[str, Any], p: dict[str, str], previous_label: str | None) -> dict[str, Any]:
    """Next period's starting storyline: keep structure and wording, clear every number so nothing
    from the previous period is presented as current, and stamp the new period."""
    s = copy.deepcopy(storyline)
    s.pop("sources", None)
    s["period"] = {"start": p["start"], "end_exclusive": p["end_exclusive"], "key": p["key"]}
    note = f"Structure carried forward{f' from {previous_label}' if previous_label else ''}; numbers cleared — enter this period's figures."
    for sl in s.get("slides", []):
        t = sl.get("type")
        if t == "cover":
            sl["kicker"] = p["label"][:80]
        elif t == "kpis":
            for k in sl.get("kpis", []):
                k["value"] = "—"
                for f in ("delta", "metric_ref", "numeric_value", "unit"):
                    k.pop(f, None)
            sl["notes"] = note
        elif t == "chart":
            for series in sl.get("chart", {}).get("series", []):
                series["values"] = [None for _ in series.get("values", [])]
                series.pop("metric_refs", None)
            sl["insights"] = []
            sl["notes"] = note
        elif t == "table":
            sl["rows"] = [[None if isinstance(c, (int, float)) and not isinstance(c, bool) else c for c in row] for row in sl.get("rows", [])]
            sl.pop("metric_refs", None)
    return s
