"""Slack workflow service (batch I2/I3).

The complete, non-destructive loop:

    mention/DM received -> DayPilot notification -> AI reply draft
                        -> user approves/edits/rejects -> approved reply sent

Draft-only by default: an inbound event only ever produces a notification and a
draft. Sending is a separate, explicit step routed through the Integration
Gateway's write path, so it always requires an approval.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event, IntegrationConnection

from ..security.injection_guard import scan
from .automation import AutomationRules, event_allowed
from .service import _audit, execute_action

# Map a raw Slack event type to the normalized IntegrationEvent type.
_TYPE_MAP = {
    "app_mention": "mention.created",
    "message.im": "message.received",
    "message": "message.received",
}


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw Slack event to DayPilot's IntegrationEvent shape."""
    etype = _TYPE_MAP.get(raw.get("type", ""), "mention.created")
    text = str(raw.get("text", ""))
    sender = str(raw.get("user", "someone"))
    return {
        "provider": "slack",
        "type": etype,
        "channel": str(raw.get("channel", "")),
        "ts": str(raw.get("ts", "")),
        "title": f"Slack {etype.split('.')[0]} from {sender}",
        "summary": text[:200],
        "severity": "approval",
        "occurredAt": datetime.utcnow().isoformat(),
    }


def ingest_event(
    session: Session,
    connection_id: str,
    raw: dict[str, Any],
    rules: AutomationRules | None = None,
    *,
    hour: int | None = None,
) -> dict[str, Any]:
    """Handle an inbound Slack event: screen it, apply automation rules, create a
    notification, and prepare a reply draft. Never sends."""
    conn = session.get(IntegrationConnection, connection_id)
    if conn is None or conn.provider != "slack":
        raise KeyError(connection_id)
    rules = rules or AutomationRules()
    event = normalize_event(raw)

    # Screen external content before any AI step; injected instructions can never
    # grant permissions — they are flagged and surfaced, not acted on.
    report = scan(event["summary"], source="slack")

    allowed, reason = event_allowed(event["type"], event["channel"], rules, hour=hour)

    # A notification is always created so the activity is visible.
    session.add(Event(
        workspace_id=conn.workspace_id,
        type="integration.notification",
        payload_json={
            "provider": "slack", "connectionId": conn.id, "type": event["type"],
            "title": event["title"], "summary": event["summary"],
            "channel": event["channel"], "ts": event["ts"],
            "severity": event["severity"], "flagged": report.flagged,
        },
    ))

    if not allowed:
        _audit(session, "integration.slack.skipped", "low", "skipped",
               {"connectionId": conn.id, "reason": reason, "channel": event["channel"]})
        session.flush()
        return {"status": "skipped", "reason": reason, "event": event, "flagged": report.flagged}

    draft = draft_reply(event["summary"])
    _audit(session, "integration.slack.drafted", "low", "recorded",
           {"connectionId": conn.id, "channel": event["channel"], "ts": event["ts"], "flagged": report.flagged})
    session.flush()
    return {
        "status": "drafted",       # draft-only — nothing is sent
        "event": event,
        "draft": draft,
        "flagged": report.flagged,
        "mode": rules.mode,
    }


def draft_reply(incoming: str) -> str:
    """Deterministic, safe reply draft (a model can replace this later)."""
    lowered = incoming.lower()
    if "deadline" in lowered or "date" in lowered or "timeline" in lowered:
        return ("Thanks for the note — we're reviewing the revised delivery date and will "
                "confirm today. I'll flag the one open dependency if it affects the timeline.")
    if "?" in incoming:
        return ("Good question — I'll pull the details together and follow up shortly with a "
                "clear answer.")
    return "Thanks for the message — I've noted it and will follow up shortly."


def request_send(session: Session, connection_id: str, channel: str, text: str) -> dict[str, Any]:
    """Send an (edited) reply. Routed through the gateway write path, so it opens
    an approval and does not post until approved."""
    return execute_action(session, connection_id, "chat.send", {"channel": channel, "text": text})
