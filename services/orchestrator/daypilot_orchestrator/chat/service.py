"""Chat-session persistence service.

Durable store for the assistant's conversations so they survive refreshes and
can be resumed, renamed, cleared, and deleted (ChatGPT / Claude style). This
module is intentionally storage-only: intent routing and provider calls happen
elsewhere (the connected assistant), and every turn is persisted here verbatim.
No credentials or provider keys are ever written — only conversation text.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import ChatMessage, ChatSession
from daypilot_knowledge.db.models import utcnow

_TITLE_MAX = 60


def _session_dict(s: ChatSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "messageCount": s.message_count,
        "lastMessageAt": s.last_message_at.isoformat() if s.last_message_at else None,
        "createdAt": s.created_at.isoformat() if s.created_at else None,
        "updatedAt": s.updated_at.isoformat() if s.updated_at else None,
    }


def _message_dict(m: ChatMessage) -> dict[str, Any]:
    return {
        "id": m.id,
        "role": m.role,
        "body": m.body,
        "action": m.action_json or None,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
    }


def list_sessions(session: Session, workspace_id: str) -> dict[str, Any]:
    """Most-recent-first list of conversations for the workspace."""
    rows = session.execute(
        select(ChatSession)
        .where(ChatSession.workspace_id == workspace_id)
        .order_by(ChatSession.updated_at.desc())
    ).scalars()
    return {"sessions": [_session_dict(s) for s in rows]}


def create_session(session: Session, workspace_id: str, title: str | None = None) -> dict[str, Any]:
    row = ChatSession(workspace_id=workspace_id, title=(title or "New conversation").strip()[:200] or "New conversation")
    session.add(row)
    session.flush()
    return _session_dict(row)


def _require(session: Session, workspace_id: str, session_id: str) -> ChatSession:
    row = session.get(ChatSession, session_id)
    if row is None or row.workspace_id != workspace_id:
        raise KeyError(session_id)
    return row


def get_session_with_messages(session: Session, workspace_id: str, session_id: str) -> dict[str, Any]:
    row = _require(session, workspace_id, session_id)
    msgs = session.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.seq.asc())
    ).scalars()
    return {**_session_dict(row), "messages": [_message_dict(m) for m in msgs]}


def rename_session(session: Session, workspace_id: str, session_id: str, title: str) -> dict[str, Any]:
    row = _require(session, workspace_id, session_id)
    row.title = (title or "").strip()[:200] or row.title
    row.updated_at = utcnow()
    session.flush()
    return _session_dict(row)


def delete_session(session: Session, workspace_id: str, session_id: str) -> dict[str, Any]:
    row = _require(session, workspace_id, session_id)
    session.delete(row)
    session.flush()
    return {"deleted": session_id}


def clear_messages(session: Session, workspace_id: str, session_id: str) -> dict[str, Any]:
    """Empty a conversation but keep the session (like 'Clear chat')."""
    row = _require(session, workspace_id, session_id)
    session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
    row.message_count = 0
    row.last_message_at = None
    row.updated_at = utcnow()
    session.flush()
    return {"cleared": session_id}


def append_message(
    session: Session,
    workspace_id: str,
    session_id: str,
    role: str,
    body: str,
    action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one turn and keep the session's counters/preview in sync.

    The first user message auto-titles an untitled session from its text, so the
    history list reads well without the user naming every conversation.
    """
    row = _require(session, workspace_id, session_id)
    role = role if role in ("user", "assistant") else "user"
    msg = ChatMessage(session_id=session_id, role=role, body=body or "", action_json=action or {})
    session.add(msg)
    now = utcnow()
    row.message_count = (row.message_count or 0) + 1
    row.last_message_at = now
    row.updated_at = now
    if role == "user" and row.title == "New conversation" and body.strip():
        row.title = body.strip()[:_TITLE_MAX]
    session.flush()
    return _message_dict(msg)
