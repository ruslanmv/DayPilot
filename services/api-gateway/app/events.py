"""Today Context event stream.

Plan changes, block transitions, approvals, agent state changes, and raised
blockers are appended to the durable `events` table with a monotonic `seq`.
Clients tail them over Server-Sent Events and resume from the last `seq` they
saw, so a reconnect never misses or replays an event.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event

from .db import _get_sessionmaker
from .serializers import serialize_event

# Canonical Today Context event types.
EVENT_TYPES = frozenset(
    {
        "plan.updated",
        "block.started",
        "approval.requested",
        "agent.state_changed",
        "blocker.raised",
    }
)

POLL_INTERVAL_SECONDS = 1.0
HEARTBEAT_EVERY = 15  # poll cycles between comment heartbeats


def record_event(
    session: Session,
    event_type: str,
    payload: dict[str, Any],
    *,
    workspace_id: str = "default",
) -> Event:
    """Append an event. Unknown types are allowed but flagged in the payload."""
    event = Event(
        workspace_id=workspace_id,
        type=event_type,
        payload_json={**payload, **({} if event_type in EVENT_TYPES else {"_unknownType": True})},
    )
    session.add(event)
    session.flush()  # assign seq without ending the caller's transaction
    return event


def list_events_since(
    session: Session, *, workspace_id: str, after_seq: int, limit: int
) -> list[Event]:
    stmt = (
        select(Event)
        .where(Event.workspace_id == workspace_id, Event.seq > after_seq)
        .order_by(Event.seq.asc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars())


def _latest_seq(session: Session, workspace_id: str) -> int:
    stmt = (
        select(Event.seq)
        .where(Event.workspace_id == workspace_id)
        .order_by(Event.seq.desc())
        .limit(1)
    )
    result = session.execute(stmt).scalar()
    return int(result) if result is not None else 0


async def event_stream(workspace_id: str, last_seq: int) -> AsyncIterator[str]:
    """Yield SSE frames for events after `last_seq`, then live-tail new ones."""
    session_factory = _get_sessionmaker()
    cursor = last_seq
    cycles = 0
    while True:
        with session_factory() as session:
            rows = list_events_since(
                session, workspace_id=workspace_id, after_seq=cursor, limit=200
            )
        if rows:
            for event in rows:
                cursor = event.seq
                data = json.dumps(serialize_event(event), separators=(",", ":"))
                yield f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"
            cycles = 0
        else:
            cycles += 1
            if cycles >= HEARTBEAT_EVERY:
                cycles = 0
                yield ": heartbeat\n\n"
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
