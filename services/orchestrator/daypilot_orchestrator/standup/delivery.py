"""Bind standup delivery to the Integration Gateway.

The standup service takes a ``send`` callable and a ``read_history`` callable
rather than a Slack token, so the engine can be tested without a workspace.
This module supplies the production implementations, routed through the
gateway so the send is audited like every other outbound write.

The send is executed directly rather than opening a second Approval: the 18:00
review *is* the approval, and it approved this exact text (proved by the
content hash). Asking again at 09:00 the next morning would mean two decisions
per day for one update, which is how a daily assistant becomes a chore.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..integrations.credentials import credential_store
from ..integrations.registry import build_provider
from daypilot_knowledge.db import IntegrationConnection


def epoch_seconds(moment: datetime) -> float:
    """Epoch seconds for a naive-UTC timestamp.

    ``datetime.timestamp()`` on a naive value interprets it in the *machine's*
    local timezone. Every timestamp in this package is naive UTC, so calling it
    directly would shift the Slack search window by the host's offset — and
    silently find no reminder on any server not set to UTC.
    """
    return moment.replace(tzinfo=timezone.utc).timestamp()


def _provider(session: Session, connection_id: str):
    conn = session.get(IntegrationConnection, connection_id)
    if conn is None:
        raise LookupError(f"integration connection {connection_id} not found")
    prov = build_provider(conn.provider)
    prov.connect(credential_store().get(conn.id))
    return conn, prov


def slack_sender(session: Session, connection_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A ``send`` for :func:`standup.service.deliver`."""

    def send(payload: dict[str, Any]) -> dict[str, Any]:
        conn, prov = _provider(session, connection_id)
        result = prov.execute("chat.send", payload)
        conn.last_activity_at = datetime.utcnow()
        session.flush()
        return result

    return send


def slack_history_reader(
    session: Session, connection_id: str,
) -> Callable[[str, datetime, datetime], list[dict[str, Any]]]:
    """A ``read_history`` for thread resolution.

    Reads are permitted immediately by the gateway's permission model, which is
    what lets DayPilot look for the morning's reminder without a second
    approval prompt.
    """

    def read(channel: str, opens: datetime, closes: datetime) -> list[dict[str, Any]]:
        _conn, prov = _provider(session, connection_id)
        result = prov.execute("chat.history", {
            "channel": channel,
            # Slack's oldest/latest are epoch seconds, inclusive.
            "oldest": f"{epoch_seconds(opens):.6f}",
            "latest": f"{epoch_seconds(closes):.6f}",
            "limit": 100,
        })
        return list(result.get("messages") or [])

    return read
