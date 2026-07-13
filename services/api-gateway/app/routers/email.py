from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.email import service as email_service
from daypilot_orchestrator.email.policy import (
    EmailActionForbidden,
    EmailApprovalRequired,
    email_enabled,
)
from daypilot_orchestrator.email.providers.registry import get_adapter

from ..db import get_session

router = APIRouter(prefix="/v1/email", tags=["email"])


def _require_enabled() -> None:
    if not email_enabled():
        raise HTTPException(status_code=404, detail="Email feature is disabled")


class DraftReplyBody(BaseModel):
    uid: str
    tone: str = "professional"
    signature: str | None = None
    workspaceId: str = "default"


class ApprovalPayload(BaseModel):
    confirmed_by_user: bool = False
    visible_action_text: str = ""


class SendBody(BaseModel):
    draftUid: str
    to: list[str]
    subject: str
    text: str
    workspaceId: str = "default"
    approval: ApprovalPayload = ApprovalPayload()


class CreateTaskBody(BaseModel):
    uid: str
    title: str
    projectId: str | None = None
    workspaceId: str = "default"


class ReviseBody(BaseModel):
    uid: str
    current: str
    instruction: str
    tone: str = "professional"
    workspaceId: str = "default"


# Providers the onboarding screen can offer. gmail/microsoft ride OAuth; imap is
# available only where the production infra is configured.
_ONBOARDING_PROVIDERS = [
    {"id": "microsoft", "label": "Microsoft 365", "auth": "oauth"},
    {"id": "google", "label": "Gmail", "auth": "oauth"},
    {"id": "imap", "label": "Other email provider (IMAP/SMTP)", "auth": "imap"},
]


@router.get("/status")
def status() -> dict[str, Any]:
    """Real connection status. Always reachable (no 404 storm). When no account
    is connected, returns the onboarding providers so the UI shows a genuine
    connect-your-email state rather than fabricated data."""
    if not email_enabled():
        return {"enabled": False, "connected": False, "account": None, "providers": _ONBOARDING_PROVIDERS}
    return {"enabled": True, **email_service.account_status(get_adapter())}


@router.get("/messages/{uid}")
def message(uid: str, folder: str = "INBOX") -> dict[str, Any]:
    """Fetch one real message/thread for the reading pane (read-only)."""
    _require_enabled()
    return email_service.message_detail(get_adapter(), uid, folder=folder)


@router.post("/ai/revise")
def ai_revise(body: ReviseBody) -> dict[str, Any]:
    """Revise the current real draft against an instruction (never sends)."""
    _require_enabled()
    return email_service.revise_reply(get_adapter(), body.uid, body.current, body.instruction, body.tone)


@router.get("/folders")
def folders() -> dict[str, Any]:
    _require_enabled()
    return {"folders": get_adapter().list_folders()}


@router.get("/messages")
def messages(session: Session = Depends(get_session), workspaceId: str = "default", q: str | None = None) -> dict[str, Any]:
    _require_enabled()
    items = email_service.sync_inbox(session, get_adapter(), workspaceId)
    if q:
        needle = q.lower()
        items = [i for i in items if needle in (i.get("subject", "") + " " + i.get("sender", "")).lower()]
    return {"items": items, "query": q}


@router.post("/messages/{uid}/draft-reply", status_code=201)
def draft_reply(uid: str, body: DraftReplyBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return email_service.draft_reply(
        session, get_adapter(), body.workspaceId, uid, body.tone, body.signature
    )


@router.post("/drafts/send")
def send(body: SendBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Send a draft. Requires an approved approval AND an explicit approval payload."""
    _require_enabled()
    try:
        return email_service.send_draft(
            session, get_adapter(), body.workspaceId, body.draftUid,
            body.to, body.subject, body.text, approved=body.approval.confirmed_by_user,
        )
    except EmailApprovalRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except EmailActionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/messages/{uid}/create-task", status_code=201)
def create_task(uid: str, body: CreateTaskBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return email_service.create_task_from_email(
        session, body.workspaceId, uid, body.title, body.projectId
    )
