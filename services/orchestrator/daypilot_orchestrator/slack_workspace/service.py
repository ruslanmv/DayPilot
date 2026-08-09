"""The Slack workspace: trace, classify, draft, refine, and never send.

The one invariant this module exists to hold:

    **No path through this file posts to Slack.**

Ingest classifies and may prepare a draft. Refinement rewrites a draft. Sending
calls :func:`daypilot_orchestrator.integrations.slack.request_send`, which routes
through the Integration Gateway's write path — so it opens an Approval and a
durable Job and posts only after a human decision. There is no flag, no setting
and no "trusted" branch that skips it.

The order of the pipeline is also load-bearing:

    normalize → injection scan → classify → (draft? stop here if not)
              → assemble authorized context → filter for the recipient
              → compose → persist

Injection screening happens before anything reads the text for meaning, and the
recipient filter happens before composition — so a fact the recipient may not
hear is never in the material the draft is built from.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    Event,
    IntegrationConnection,
    SlackConversation,
    SlackDraft,
    SlackDraftRevision,
    SlackMessage,
)

from ..integrations.service import _audit
from ..integrations.slack import request_send
from ..security.injection_guard import scan
from . import classify as cls
from . import compose, settings
from .context import assemble, redact_for_recipient

#: The optional product surface. The Slack *provider* exists regardless; this
#: gates the workspace UI and its pipeline.
FLAG = "DAYPILOT_SLACK_WORKSPACE_ENABLED"

DRAFT = "draft"
SENDING = "sending"
SENT = "sent"
FAILED = "failed"
DISCARDED = "discarded"

#: A draft in one of these states is finished; refinement and sending refuse.
TERMINAL = frozenset({SENT, DISCARDED})


class DraftLocked(RuntimeError):
    """The draft can no longer be edited or sent."""


class NotConnected(RuntimeError):
    """No Slack connection to send through."""


def workspace_enabled() -> bool:
    return str(os.getenv(FLAG, "")).strip().lower() in ("1", "true", "yes", "on")


# --- connection ---------------------------------------------------------------

def connection(session: Session, workspace_id: str) -> IntegrationConnection | None:
    return session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.provider == "slack",
        )
    ).scalars().first()


def status(session: Session, workspace_id: str = "default") -> dict[str, Any]:
    conn = connection(session, workspace_id)
    prefs = settings.get_preferences(session, workspace_id)
    live = conn is not None and conn.status == "connected"
    counts = inbox_counts(session, workspace_id) if live else {}
    return {
        "enabled": workspace_enabled(),
        "connected": bool(live),
        "connectionId": conn.id if conn else None,
        "account": (conn.detail or "").strip() or None if conn else None,
        "capabilities": list(conn.capabilities or []) if conn else [],
        "lastActivityAt": conn.last_activity_at.isoformat() if conn and conn.last_activity_at else None,
        "accessMode": prefs.access_mode,
        # Personal DMs need user-scoped authorization; the bot token does not
        # carry it, and saying otherwise would be a promise the API cannot keep.
        "personalMessagesAvailable": prefs.access_mode == "personal",
        "counts": counts,
        "sendsRequireApproval": True,
    }


# --- tracing ------------------------------------------------------------------

def upsert_conversation(
    session: Session, workspace_id: str, *, channel_id: str, kind: str = "channel",
    name: str = "", counterpart: str = "", audience: str = "internal",
    connection_id: str | None = None, member_count: int = 0,
) -> SlackConversation:
    row = session.execute(
        select(SlackConversation).where(
            SlackConversation.workspace_id == workspace_id,
            SlackConversation.channel_id == channel_id,
        )
    ).scalars().first()
    if row is None:
        row = SlackConversation(workspace_id=workspace_id, channel_id=channel_id)
        session.add(row)
    row.kind = kind or row.kind
    row.name = name or row.name
    row.counterpart = counterpart or row.counterpart
    row.audience = audience or row.audience
    row.connection_id = connection_id or row.connection_id
    row.member_count = member_count or row.member_count
    session.flush()
    return row


def recent_messages(
    session: Session, conversation_id: str, limit: int = 6
) -> list[SlackMessage]:
    return list(session.execute(
        select(SlackMessage)
        .where(SlackMessage.conversation_id == conversation_id)
        .order_by(SlackMessage.occurred_at.desc())
        .limit(limit)
    ).scalars())


def ingest(
    session: Session,
    workspace_id: str,
    raw: dict[str, Any],
    *,
    connected_providers: set[str] | None = None,
) -> dict[str, Any]:
    """Trace one Slack message and prepare a draft when it earns one."""
    channel_id = str(raw.get("channel") or "")
    ts = str(raw.get("ts") or "")
    text = str(raw.get("text") or "")
    if not channel_id or not ts:
        raise ValueError("a Slack message needs a channel and a ts")

    kind = str(raw.get("channelKind") or ("im" if channel_id.startswith("D") else "channel"))
    conv = upsert_conversation(
        session, workspace_id, channel_id=channel_id, kind=kind,
        name=str(raw.get("channelName") or ""),
        counterpart=str(raw.get("userName") or ""),
        audience=str(raw.get("audience") or "internal"),
        member_count=int(raw.get("memberCount") or 0),
    )

    # Screen before anything reads the text for meaning. An instruction hidden
    # in a message can be flagged and shown, never obeyed.
    report = scan(text, source="slack")

    mentioned = bool(raw.get("mentioned"))
    direction = "outgoing" if raw.get("direction") == "outgoing" else "incoming"
    classification = (
        cls.classify(text, mentioned=mentioned, is_dm=kind in ("im", "mpim"))
        if direction == "incoming" else cls.LOW_PRIORITY
    )

    existing = session.execute(
        select(SlackMessage).where(
            SlackMessage.conversation_id == conv.id, SlackMessage.ts == ts,
        )
    ).scalars().first()
    if existing is not None:
        return {"status": "duplicate", "messageId": existing.id,
                "classification": existing.classification}

    message = SlackMessage(
        workspace_id=workspace_id, conversation_id=conv.id, ts=ts,
        thread_ts=str(raw.get("thread_ts") or "") or None,
        author_id=str(raw.get("user") or ""), author_name=str(raw.get("userName") or ""),
        direction=direction, text=text, classification=classification,
        flagged=report.flagged,
    )
    session.add(message)
    conv.last_message_at = datetime.utcnow()
    session.flush()

    session.add(Event(
        workspace_id=workspace_id, type="slack.message.traced",
        payload_json={"conversationId": conv.id, "messageId": message.id,
                      "classification": classification, "flagged": report.flagged},
    ))

    prefs = settings.get_preferences(session, workspace_id)
    if direction == "outgoing":
        return {"status": "traced", "messageId": message.id, "classification": classification}
    if not prefs.auto_prepare:
        return {"status": "traced", "messageId": message.id, "classification": classification,
                "reason": "auto_prepare_off"}
    if not settings.drafting_allowed(prefs, kind=kind, mentioned=mentioned):
        return {"status": "traced", "messageId": message.id, "classification": classification,
                "reason": "not_in_drafting_scope"}
    if not cls.should_draft(classification):
        # The most valuable outcome: a "thanks 👍" gets shown, not answered.
        return {"status": "traced", "messageId": message.id, "classification": classification,
                "reason": "no_reply_needed"}

    draft = prepare_draft(
        session, workspace_id, conversation=conv, message=message,
        connected_providers=connected_providers,
    )
    return {"status": "drafted", "messageId": message.id,
            "classification": classification, "draftId": draft.id,
            "flagged": report.flagged}


# --- drafting -----------------------------------------------------------------

def prepare_draft(
    session: Session,
    workspace_id: str,
    *,
    conversation: SlackConversation,
    message: SlackMessage | None = None,
    instruction: str = "",
    connected_providers: set[str] | None = None,
) -> SlackDraft:
    """Assemble authorized context, filter it for the recipient, and compose."""
    prefs = settings.get_preferences(session, workspace_id)
    allowed = set(settings.allowed_context_sources(session, workspace_id, connected_providers))

    seed = message.text if message is not None else instruction
    history = recent_messages(session, conversation.id) if prefs.use_previous_conversations else []
    sources, _project = assemble(
        session, workspace_id, text=seed, recent_messages=history, allowed_sources=allowed,
    )
    context = redact_for_recipient(
        sources, conversation.audience, enabled=prefs.recipient_protection,
    )

    classification = message.classification if message is not None else cls.NEEDS_REPLY
    text = compose.draft_text(
        context,
        classification=classification,
        style=compose.style_for(conversation.kind),
        counterpart=conversation.counterpart,
    )

    draft = SlackDraft(
        workspace_id=workspace_id, conversation_id=conversation.id,
        message_id=message.id if message is not None else None,
        kind="reply" if message is not None else "compose",
        text=text, status=DRAFT, classification=classification,
        sources_json=context.serialize_sources(), withheld_json=context.withheld,
        backend="deterministic",
    )
    session.add(draft)
    session.flush()
    _audit(session, "slack.draft.prepared", "low", "recorded",
           {"draftId": draft.id, "conversationId": conversation.id,
            "sources": len(draft.sources_json), "withheld": len(draft.withheld_json)})
    return draft


def _editable(draft: SlackDraft) -> None:
    if draft.status in TERMINAL:
        raise DraftLocked(f"draft is {draft.status}")


def update_text(session: Session, draft: SlackDraft, text: str) -> SlackDraft:
    """A manual edit. Recorded as a revision so it can be undone like any other."""
    _editable(draft)
    if text != draft.text:
        session.add(SlackDraftRevision(
            draft_id=draft.id, previous_text=draft.text, instruction="manual edit",
        ))
        draft.text = text
        session.flush()
    return draft


def apply_transform(session: Session, draft: SlackDraft, kind: str) -> SlackDraft:
    _editable(draft)
    if kind not in compose.TRANSFORMS:
        raise ValueError(f"unknown transform '{kind}'")
    return update_text(session, draft, compose.transform(draft.text, kind))


def propose_refinement(draft: SlackDraft, instruction: str) -> dict[str, Any]:
    """Return a candidate revision **without** applying it.

    The assistant proposing a rewrite must not silently replace what the user
    wrote: it offers, and "Use this" is a separate decision. That is the whole
    difference between a tool you can experiment with and one you have to watch.
    """
    _editable(draft)
    proposed = compose.refine(draft.text, instruction)
    return {
        "draftId": draft.id,
        "instruction": instruction,
        "current": draft.text,
        "proposed": proposed,
        "changed": proposed.strip() != (draft.text or "").strip(),
    }


def accept_refinement(session: Session, draft: SlackDraft, text: str, instruction: str = "") -> SlackDraft:
    _editable(draft)
    session.add(SlackDraftRevision(
        draft_id=draft.id, previous_text=draft.text, instruction=instruction,
    ))
    draft.text = text
    session.flush()
    return draft


def undo(session: Session, draft: SlackDraft) -> SlackDraft:
    """Step back one revision."""
    _editable(draft)
    revision = session.execute(
        select(SlackDraftRevision)
        .where(SlackDraftRevision.draft_id == draft.id)
        .order_by(SlackDraftRevision.created_at.desc())
    ).scalars().first()
    if revision is None:
        return draft
    draft.text = revision.previous_text
    session.delete(revision)
    session.flush()
    return draft


# --- sending ------------------------------------------------------------------

def send(session: Session, workspace_id: str, draft: SlackDraft) -> dict[str, Any]:
    """Request delivery. Opens an approval; does **not** post.

    The Integration Gateway classifies ``chat.send`` as a WRITE, so this returns
    ``approval_required`` and a job that stays blocked until a human decides it.
    Nothing in this module can shortcut that, which is the point.
    """
    _editable(draft)
    if not (draft.text or "").strip():
        raise ValueError("refusing to send an empty draft")
    conn = connection(session, workspace_id)
    if conn is None or conn.status != "connected":
        raise NotConnected("no connected Slack workspace")
    conversation = session.get(SlackConversation, draft.conversation_id or "")
    if conversation is None:
        raise ValueError("draft has no conversation to send to")

    result = request_send(session, conn.id, conversation.channel_id, draft.text)
    draft.status = SENDING
    draft.approval_id = str(result.get("approvalId") or "") or None
    draft.detail = str(result.get("status") or "")
    session.flush()
    _audit(session, "slack.draft.send_requested", "medium", "requested",
           {"draftId": draft.id, "channel": conversation.channel_id,
            "approvalId": draft.approval_id})
    return {"status": result.get("status", "approval_required"),
            "draftId": draft.id, "approvalId": draft.approval_id}


def discard(session: Session, draft: SlackDraft) -> SlackDraft:
    _editable(draft)
    draft.status = DISCARDED
    session.flush()
    return draft


# --- reading ------------------------------------------------------------------

def inbox_counts(session: Session, workspace_id: str) -> dict[str, int]:
    rows = session.execute(
        select(SlackMessage.classification, SlackMessage.handled).where(
            SlackMessage.workspace_id == workspace_id,
            SlackMessage.direction == "incoming",
        )
    ).all()
    counts = {"needs_reply": 0, "action": 0, "fyi": 0, "done": 0}
    for classification, handled in rows:
        if handled:
            counts["done"] += 1
            continue
        counts[cls.inbox_group(classification)] = counts.get(cls.inbox_group(classification), 0) + 1
    return counts


def serialize_draft(row: SlackDraft) -> dict[str, Any]:
    return {
        "id": row.id,
        "conversationId": row.conversation_id,
        "messageId": row.message_id,
        "kind": row.kind,
        "text": row.text,
        "status": row.status,
        "classification": row.classification,
        "sources": list(row.sources_json or []),
        "withheldCount": len(row.withheld_json or []),
        "approvalId": row.approval_id,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        # Stated on every draft so the UI never has to infer it.
        "sendsRequireApproval": True,
    }


def serialize_message(row: SlackMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts,
        "threadTs": row.thread_ts,
        "author": row.author_name or row.author_id,
        "direction": row.direction,
        "text": row.text,
        "classification": row.classification,
        "group": cls.inbox_group(row.classification),
        "flagged": bool(row.flagged),
        "handled": bool(row.handled),
        "occurredAt": row.occurred_at.isoformat() if row.occurred_at else None,
    }


def serialize_conversation(row: SlackConversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "channelId": row.channel_id,
        "kind": row.kind,
        "name": row.name,
        "counterpart": row.counterpart,
        "audience": row.audience,
        "memberCount": row.member_count,
        "lastMessageAt": row.last_message_at.isoformat() if row.last_message_at else None,
    }


def active_draft(session: Session, conversation_id: str) -> SlackDraft | None:
    """The draft currently open on a conversation, if any."""
    return session.execute(
        select(SlackDraft)
        .where(SlackDraft.conversation_id == conversation_id,
               SlackDraft.status.notin_(list(TERMINAL)))
        .order_by(SlackDraft.updated_at.desc())
    ).scalars().first()


def thread(session: Session, conversation: SlackConversation, limit: int = 50) -> dict[str, Any]:
    """A conversation as the middle column renders it: messages oldest-first."""
    messages = list(session.execute(
        select(SlackMessage)
        .where(SlackMessage.conversation_id == conversation.id)
        .order_by(SlackMessage.occurred_at.desc())
        .limit(limit)
    ).scalars())
    draft = active_draft(session, conversation.id)
    return {
        "conversation": serialize_conversation(conversation),
        "messages": [serialize_message(m) for m in reversed(messages)],
        "draft": serialize_draft(draft) if draft else None,
    }


def mark_handled(session: Session, message: SlackMessage, handled: bool = True) -> SlackMessage:
    """Move a message into (or out of) Done.

    Reversible on purpose: an inbox where "Done" is a one-way door makes people
    hesitate before clicking it, and an inbox people hesitate to clear stops
    being an inbox.
    """
    message.handled = bool(handled)
    session.flush()
    return message


def recipients(session: Session, workspace_id: str) -> list[dict[str, Any]]:
    """Who a new message can be addressed to.

    Only conversations DayPilot has actually seen. It would be easy to offer the
    full workspace directory here, but the honest answer is that a conversation
    DayPilot has never observed is one it has no context for — and offering it
    anyway invites a confident draft written from nothing.
    """
    rows = session.execute(
        select(SlackConversation)
        .where(SlackConversation.workspace_id == workspace_id)
        .order_by(SlackConversation.last_message_at.desc().nullslast())
        .limit(100)
    ).scalars()
    return [serialize_conversation(row) for row in rows]


def inbox(session: Session, workspace_id: str, group: str = "all") -> list[dict[str, Any]]:
    """The decision inbox: latest incoming message per conversation, with its draft."""
    messages = list(session.execute(
        select(SlackMessage)
        .where(SlackMessage.workspace_id == workspace_id,
               SlackMessage.direction == "incoming")
        .order_by(SlackMessage.occurred_at.desc())
        .limit(100)
    ).scalars())

    drafts_by_message = {
        d.message_id: d for d in session.execute(
            select(SlackDraft).where(
                SlackDraft.workspace_id == workspace_id,
                SlackDraft.status.notin_([DISCARDED]),
            )
        ).scalars() if d.message_id
    }

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.conversation_id in seen:
            continue
        seen.add(message.conversation_id)
        item_group = "done" if message.handled else cls.inbox_group(message.classification)
        if group not in ("all", item_group):
            continue
        conversation = session.get(SlackConversation, message.conversation_id)
        draft = drafts_by_message.get(message.id)
        out.append({
            "conversation": serialize_conversation(conversation) if conversation else None,
            "message": serialize_message(message),
            "group": item_group,
            "draft": serialize_draft(draft) if draft else None,
        })
    return out
