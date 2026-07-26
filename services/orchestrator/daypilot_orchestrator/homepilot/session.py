"""Per-agent conversation persistence for the HomePilot bridge (Batch A6).

Each HomePilot agent link gets its OWN durable ``ChatSession`` (``kind='agent'``,
``agent_link_id`` set), so a message to one agent never lands in another agent's
history — mixed-agent conversations never cross. The session carries a stable
``remote_session_id`` that DayPilot sends to HomePilot as ``X-HomePilot-Session-ID``
so HomePilot can maintain its own conversation continuity. HomePilot owns the
remote conversation; DayPilot stores only the reference plus the turn text.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import ChatMessage, ChatSession
from daypilot_knowledge.db.models import utcnow

_TITLE_MAX = 60
# How many prior turns to replay to HomePilot for context. Keeps the request
# bounded while giving the persona enough of the thread to stay coherent.
_HISTORY_TURNS = 20


def _message_dict(m: ChatMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "body": m.body,
        "action": m.action_json or None,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }


def resolve_session(session: Session, workspace_id: str, *, agent_link_id: str, agent_name: str) -> ChatSession:
    """Find this agent's conversation, or create it. Idempotent per (workspace,
    agent_link_id) so every turn resumes the same thread."""
    row = session.execute(
        select(ChatSession).where(
            ChatSession.workspace_id == workspace_id,
            ChatSession.kind == "agent",
            ChatSession.agent_link_id == agent_link_id,
        )
    ).scalars().first()
    if row is not None:
        return row
    row = ChatSession(
        workspace_id=workspace_id,
        kind="agent",
        agent_link_id=agent_link_id,
        title=(agent_name or "Agent").strip()[:200] or "Agent",
        remote_session_id=uuid.uuid4().hex,
    )
    session.add(row)
    session.flush()
    return row


def load_messages(session: Session, chat_session_id: str) -> list[dict[str, Any]]:
    msgs = session.execute(
        select(ChatMessage).where(ChatMessage.session_id == chat_session_id).order_by(ChatMessage.seq.asc())
    ).scalars()
    return [_message_dict(m) for m in msgs]


def history_as_messages(session: Session, chat_session_id: str) -> list[dict[str, str]]:
    """Recent turns as OpenAI-style ``{role, content}`` for the persona call.

    Only the persisted user/assistant text is replayed — never the stored
    proposal metadata. Trimmed to the last ``_HISTORY_TURNS`` turns.
    """
    rows = session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.seq.desc())
        .limit(_HISTORY_TURNS)
    ).scalars().all()
    rows.reverse()
    out: list[dict[str, str]] = []
    for m in rows:
        role = "assistant" if m.role == "assistant" else "user"
        out.append({"role": role, "content": m.body or ""})
    return out


def append_turn(
    session: Session,
    chat: ChatSession,
    role: str,
    body: str,
    action: dict[str, Any] | None = None,
) -> ChatMessage:
    """Append one turn to an agent conversation and keep counters in sync."""
    role = "assistant" if role == "assistant" else "user"
    msg = ChatMessage(session_id=chat.id, role=role, body=body or "", action_json=action or {})
    session.add(msg)
    now = utcnow()
    chat.message_count = (chat.message_count or 0) + 1
    chat.last_message_at = now
    chat.updated_at = now
    session.flush()
    return msg


def message_dict(m: ChatMessage) -> dict[str, Any]:
    return _message_dict(m)
