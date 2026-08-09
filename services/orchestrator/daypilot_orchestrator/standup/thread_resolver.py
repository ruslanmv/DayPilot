"""Find the standup thread to reply into — or refuse to post at all.

The failure this module exists to prevent: posting the day's update as a new
root message in a busy channel because the reminder thread could not be found.
That is worse than posting nothing, so every path here ends in either a
resolved ``thread_ts`` or an honest :class:`ThreadNotFound`.

Two strategies:

* **own** — DayPilot posted the reminder itself and kept the timestamp. Exact.
* **adopt** — somebody else's Slack workflow posts the reminder. Matched on
  three signals together (time window, bot identity, text signature), because
  any one of them alone is a bad bet to make daily in a public channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from . import schedule
from .policy import ThreadNotFound

#: A Slack `ts` is seconds-since-epoch with microseconds ("1722850800.000100").
#: Comparing it to a window means comparing it as a float, not as a string.
def _ts_to_datetime(ts: str) -> datetime | None:
    try:
        return datetime.utcfromtimestamp(float(ts))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ResolvedThread:
    ts: str
    text: str
    matched_on: list[str]
    bot_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "text": self.text, "matchedOn": list(self.matched_on),
                "botId": self.bot_id}


#: Reads a channel's recent root messages. Injected so resolution is testable
#: without Slack, and so the caller decides how the integration gateway is
#: reached.
HistoryReader = Callable[[str, datetime, datetime], list[dict[str, Any]]]


def _score(
    message: dict[str, Any],
    *,
    signature: str,
    bot_id: str | None,
    opens: datetime,
    closes: datetime,
) -> tuple[int, list[str]]:
    """How confident we are that this message is today's standup reminder."""
    matched: list[str] = []

    moment = _ts_to_datetime(str(message.get("ts") or ""))
    if moment is None or not (opens <= moment <= closes):
        return 0, []
    matched.append("time_window")

    # A reply is never the reminder — the reminder is what replies hang off.
    thread_ts = message.get("threadTs")
    if thread_ts and str(thread_ts) != str(message.get("ts")):
        return 0, []

    text = str(message.get("text") or "")
    if signature and signature.lower() in text.lower():
        matched.append("signature")

    observed_bot = message.get("botId")
    if bot_id and observed_bot and str(observed_bot) == str(bot_id):
        matched.append("bot_identity")

    # Time alone is not enough to post under someone's name. Either the wording
    # or the identity of the poster has to agree as well.
    score = len(matched)
    return (score if score >= 2 else 0), matched


def resolve(
    *,
    read_history: HistoryReader,
    channel_id: str,
    standup_day: date,
    timezone_name: str,
    reminder_time: str,
    signature: str = "Daily Standup Reminder",
    bot_id: str | None = None,
    known_thread_ts: str | None = None,
) -> ResolvedThread:
    """Resolve the thread root for ``standup_day``.

    ``known_thread_ts`` short-circuits the search for the ``own`` strategy,
    where DayPilot already holds the timestamp of the reminder it posted.
    """
    if known_thread_ts:
        return ResolvedThread(ts=str(known_thread_ts), text="", matched_on=["own_reminder"])

    opens, closes = schedule.thread_search_window(
        timezone_name=timezone_name,
        standup_day=standup_day,
        reminder_time=reminder_time,
    )
    messages = read_history(channel_id, opens, closes) or []

    best: tuple[int, ResolvedThread] | None = None
    for message in messages:
        score, matched = _score(
            message, signature=signature, bot_id=bot_id, opens=opens, closes=closes,
        )
        if score == 0:
            continue
        candidate = ResolvedThread(
            ts=str(message.get("ts")),
            text=str(message.get("text") or ""),
            matched_on=matched,
            bot_id=(str(message["botId"]) if message.get("botId") else None),
        )
        # A later message wins a tie: if the workflow posted twice, the update
        # belongs in the thread people are actually replying to today.
        if best is None or score > best[0] or (
            score == best[0] and float(candidate.ts) > float(best[1].ts)
        ):
            best = (score, candidate)

    if best is None:
        raise ThreadNotFound(
            f"no standup reminder matching {signature!r} found in {channel_id} "
            f"between {opens.isoformat()}Z and {closes.isoformat()}Z"
        )
    return best[1]


def describe_for_setup(thread: ResolvedThread, channel_name: str) -> dict[str, Any]:
    """What the setup screen shows so the user can confirm the match once.

    Confirming a real message beats trusting a regex: the user sees the exact
    text DayPilot will reply under, before it ever posts.
    """
    preview = thread.text.strip().splitlines()
    return {
        "found": True,
        "threadTs": thread.ts,
        "channelName": channel_name,
        "preview": preview[0][:200] if preview else "",
        "matchedOn": list(thread.matched_on),
        "message": (
            f"We found today's Daily Standup message in #{channel_name}. "
            "Replies will be posted inside this thread."
        ),
    }
