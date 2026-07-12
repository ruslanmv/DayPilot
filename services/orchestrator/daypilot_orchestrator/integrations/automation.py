"""Minimal automation rules for integrations (batch I3).

Basic controls only — no automation graph. Defaults are conservative:
draft-only, and a per-hour reply cap. Sending always still requires an approval;
these rules gate whether DayPilot even drafts/acknowledges an event.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutomationRules:
    # None means "all channels". Otherwise only these channel ids are handled.
    allowed_channels: set[str] | None = None
    allowed_types: set[str] = field(default_factory=lambda: {"app_mention", "message.im", "mention.created"})
    # (start_hour, end_hour) in 24h local time; None means always on.
    business_hours: tuple[int, int] | None = None
    # "draft_only" (never sends) or "auto_ack" (a bounded, approval-gated ack).
    mode: str = "draft_only"
    max_replies_per_hour: int = 10


def event_allowed(event_type: str, channel: str, rules: AutomationRules, hour: int | None = None) -> tuple[bool, str]:
    """Return (allowed, reason). Independent of sending, which is always gated."""
    if rules.allowed_channels is not None and channel not in rules.allowed_channels:
        return False, "channel not allowed"
    if event_type not in rules.allowed_types:
        return False, "message type not allowed"
    if rules.business_hours is not None and hour is not None:
        start, end = rules.business_hours
        within = start <= hour < end if start <= end else (hour >= start or hour < end)
        if not within:
            return False, "outside business hours"
    return True, "ok"
