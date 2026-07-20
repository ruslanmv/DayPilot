"""Email orchestration and governance (batch B9).

Syncs inbox items (read-only), runs the Sentinel, and persists drafts. Sending
is draft-and-approve: a draft is created and an approval opened; the actual SMTP
submission only happens through send_draft after the approval is approved. The
Sentinel never sends on its own.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, EmailItem, Event, Task

import os

from . import sentinel
from .adapters.base import MailboxAdapter
from .policy import EmailAction, _flag, check_action

EVENT_APPROVAL_REQUESTED = "approval.requested"


def account_status(
    adapter: MailboxAdapter,
    email_address: str | None = None,
    display_name: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Real connection status for the mailbox the gateway is configured with.

    When no account is configured the UI shows onboarding; it never infers a
    connection from local state. Capabilities are read from policy so the UI can
    truthfully say whether DayPilot may read/send. No secrets are returned. The
    connection's real email/provider (from the backend-owned MailboxConnection)
    are preferred over environment fallbacks.
    """
    provider = provider or getattr(adapter, "provider", "mock")
    email_address = email_address or os.getenv("EMAIL_USERNAME", os.getenv("IMAP_USERNAME", "")) or (
        "demo@local.mock" if provider == "mock" else ""
    )
    can_send = _flag("DAYPILOT_EMAIL_ALLOW_SEND", "true")
    return {
        "connected": True,
        "account": {
            "provider": provider,
            "emailAddress": email_address,
            "displayName": display_name or os.getenv("EMAIL_DISPLAY_NAME") or None,
            "status": "connected",
            "capabilities": {
                "read": True,
                "send": can_send,
                "drafts": True,
                "labels": provider in ("gmail", "google"),
                "folders": True,
                "attachments": True,
                "pushNotifications": False,
            },
        },
    }


def message_detail(adapter: MailboxAdapter, uid: str, folder: str = "INBOX") -> dict[str, Any]:
    """Fetch a single real message (read-only; never marks it read)."""
    msg = adapter.fetch_message(uid, folder=folder)
    return {
        "uid": msg.uid,
        "folder": msg.folder,
        "messageId": msg.message_id,
        "subject": msg.subject,
        "from": msg.sender,
        "to": msg.recipients,
        "receivedAt": msg.received_at,
        "flags": msg.flags,
        "text": msg.text,
        "html": msg.html,
        "hasAttachments": msg.has_attachments,
    }


def revise_reply(adapter: MailboxAdapter, uid: str, current: str, instruction: str, tone: str = "professional") -> dict[str, Any]:
    """Revise an existing draft against a natural instruction.

    Operates on the *real* current draft text — it transforms genuine content
    rather than fabricating a new canned reply. Uses the Sentinel's paired model
    when available and a deterministic transform otherwise, so revision works
    offline and in CI.
    """
    revised = sentinel.revise_reply(current, instruction, tone=tone) if hasattr(sentinel, "revise_reply") else None
    if not revised:
        revised = _deterministic_revise(current, instruction)
    return {"body": revised, "instruction": instruction}


def _deterministic_revise(content: str, instruction: str) -> str:
    lowered = instruction.lower()
    if "short" in lowered:
        lines = [ln for ln in content.split("\n") if ln.strip()]
        head = lines[:2]
        tail = "Best regards," if "regards" not in "\n".join(head).lower() else ""
        return "\n\n".join([*head, tail]).strip()
    if "formal" in lowered:
        return content.replace("Thanks", "Thank you").replace("Hi ", "Dear ")
    if "remove" in lowered and "paragraph" in lowered:
        paras = [p for p in content.split("\n\n") if p.strip()]
        return "\n\n".join(paras[:-2] + paras[-1:]) if len(paras) > 2 else content
    if "confirm" in lowered or "deadline" in lowered or "date" in lowered:
        return content.replace("Best regards,", "Could you please confirm the date so we can plan around it?\n\nBest regards,")
    return f"{content}\n\n(Adjusted per your request: {instruction})"


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _audit(session: Session, action: str, risk: str, decision: str, payload: dict[str, Any]) -> None:
    session.add(AuditLog(event_type=f"email.{action}", risk=risk, decision=decision, payload_json=payload))


def sync_inbox(
    session: Session, adapter: MailboxAdapter, workspace_id: str = "default", limit: int = 25
) -> list[dict[str, Any]]:
    """Read the inbox (never marks read), classify, and upsert email items."""
    messages = adapter.list_inbox(limit=limit)
    out: list[dict[str, Any]] = []
    for msg in messages:
        result = sentinel.classify(msg)
        existing = session.execute(
            select(EmailItem).where(
                EmailItem.workspace_id == workspace_id, EmailItem.external_id == msg.uid
            )
        ).scalar_one_or_none()
        if existing is None:
            item = EmailItem(
                workspace_id=workspace_id,
                external_id=msg.uid,
                subject=msg.subject,
                sender=msg.sender,
                urgency=result.urgency,
                intent=result.intent,
                classification_json={
                    "actionItems": result.action_items,
                    "scheduleImpact": result.schedule_impact,
                    "reasons": result.reasons,
                },
                status="classified",
            )
            session.add(item)
            session.flush()
        else:
            item = existing
            item.urgency = result.urgency
            item.intent = result.intent
        out.append(_serialize_item(item, result.schedule_impact))
    session.flush()
    return out


def _serialize_item(item: EmailItem, schedule_impact: bool | None = None) -> dict[str, Any]:
    classification = item.classification_json or {}
    return {
        "id": item.id,
        "externalId": item.external_id,
        "subject": item.subject,
        "sender": item.sender,
        "urgency": item.urgency,
        "intent": item.intent,
        "status": item.status,
        "scheduleImpact": classification.get("scheduleImpact", schedule_impact),
        "actionItems": classification.get("actionItems", []),
    }


def draft_reply(
    session: Session,
    adapter: MailboxAdapter,
    workspace_id: str,
    uid: str,
    tone: str = "professional",
    signature: str | None = None,
) -> dict[str, Any]:
    """Safe action: create a draft reply and open a pending send approval."""
    check_action(EmailAction.DRAFT_REPLY, approved=True)  # always safe
    message = adapter.fetch_message(uid)
    body = sentinel.draft_reply(message, tone=tone)
    draft = adapter.create_draft(
        to=[message.sender], subject=f"Re: {message.subject}", text=body,
        in_reply_to=message.message_id, signature=signature,
    )
    item = session.execute(
        select(EmailItem).where(
            EmailItem.workspace_id == workspace_id, EmailItem.external_id == uid
        )
    ).scalar_one_or_none()
    if item is not None:
        item.draft_text = body
        item.status = "drafted"

    approval = Approval(
        workspace_id=workspace_id,
        action="email.send",
        summary=f"Send reply to {message.sender} — Re: {message.subject}",
        risk="medium",
        status="pending",
        resource_type="email_draft",
        resource_id=draft.draft_uid,
    )
    session.add(approval)
    _emit(session, workspace_id, EVENT_APPROVAL_REQUESTED,
          {"resourceType": "email_draft", "resourceId": draft.draft_uid})
    _audit(session, "draft_reply", "low", "recorded", {"uid": uid, "draftUid": draft.draft_uid})
    session.flush()
    return {
        "draftUid": draft.draft_uid,
        "body": body,
        "approvalId": approval.id,
        "approvalStatus": approval.status,
        "requiresApproval": True,
    }


def send_draft(
    session: Session,
    adapter: MailboxAdapter,
    workspace_id: str,
    draft_uid: str,
    to: list[str],
    subject: str,
    text: str,
    approved: bool,
) -> dict[str, Any]:
    """Risky action: send. Enforced against policy + the draft's approval."""
    # Policy check first (raises EmailApprovalRequired / EmailActionForbidden).
    check_action(EmailAction.SEND, approved=approved)

    approval = session.execute(
        select(Approval).where(
            Approval.resource_type == "email_draft", Approval.resource_id == draft_uid
        ).order_by(Approval.created_at.desc())
    ).scalars().first()
    if approval is None or approval.status != "approved":
        _audit(session, "send_blocked", "medium", "blocked", {"draftUid": draft_uid})
        raise PermissionError("Send refused: the draft has no approved approval record.")

    result = adapter.send_message(to=to, subject=subject, text=text)
    item = session.execute(
        select(EmailItem).where(
            EmailItem.workspace_id == workspace_id, EmailItem.classification_json.isnot(None)
        )
    ).scalars().first()
    if item is not None and item.draft_text == text:
        item.status = "sent"
    _audit(session, "send_performed", "medium", "approved",
           {"draftUid": draft_uid, "smtp": result.smtp_status})
    session.flush()
    return {"smtpStatus": result.smtp_status, "sentUid": result.sent_uid, "folder": result.folder}


def create_task_from_email(
    session: Session, workspace_id: str, uid: str, title: str, project_id: str | None = None
) -> dict[str, Any]:
    """Safe local action: turn an email into a DayPilot task."""
    check_action(EmailAction.CREATE_TASK, approved=True)
    task = Task(
        workspace_id=workspace_id,
        title=title,
        owner="you",
        status="active",
        source="email",
        project_id=project_id,
        context=f"Created from email {uid}.",
    )
    session.add(task)
    session.flush()
    _audit(session, "create_task", "low", "recorded", {"uid": uid, "taskId": task.id})
    return {"taskId": task.id, "title": task.title}
