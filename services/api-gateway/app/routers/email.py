from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.email import service as email_service
from daypilot_orchestrator.email.policy import (
    EmailActionForbidden,
    EmailApprovalRequired,
    email_enabled,
)

from .. import mail_setup
from ..db import get_session

router = APIRouter(prefix="/v1/email", tags=["email"])


def _require_enabled() -> None:
    if not email_enabled():
        # Structured so the UI can show a clear "disabled for this deployment"
        # state instead of treating it as a missing route. GET /status stays
        # reachable and reports enabled:false, so the UI checks that first.
        raise HTTPException(status_code=404, detail={
            "error": "email_disabled",
            "message": "Email is disabled for this deployment.",
        })


class WsBody(BaseModel):
    workspaceId: str = "default"


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


class MailboxTestBody(BaseModel):
    provider: str = "imap"
    emailAddress: str = ""
    displayName: str | None = None
    username: str | None = None
    password: str | None = None
    imapHost: str | None = None
    imapPort: int | None = None
    imapSecurity: str | None = None
    smtpHost: str | None = None
    smtpPort: int | None = None
    smtpSecurity: str | None = None
    workspaceId: str = "default"


def _demo_mail() -> bool:
    import os
    return os.getenv("DAYPILOT_EMAIL_PROVIDER", "").lower() == "mock"


@router.get("/status")
def status(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    """Real connection status. Always reachable (no 404 storm). Backed by the
    workspace's MailboxConnection — when nothing is connected the UI shows a
    genuine connect-your-email state rather than fabricated data."""
    if not email_enabled():
        return {"enabled": False, "connected": False, "account": None, **mail_setup.mailbox_status(session, workspaceId)}
    mb = mail_setup.mailbox_status(session, workspaceId)
    if not mb["connected"] and not _demo_mail():
        return {"enabled": True, "connected": False, "account": None,
                "connection": mb["connection"], "providers": mb["providers"]}
    adapter = mail_setup.adapter_for_workspace(session, workspaceId)
    conn = mb["connection"] or {}
    return {
        "enabled": True,
        "connection": mb["connection"],
        **email_service.account_status(
            adapter,
            email_address=conn.get("emailAddress"),
            display_name=conn.get("displayName"),
            provider=conn.get("provider"),
        ),
    }


# ---- mailbox setup wizard (Batch 3) -----------------------------------------

class DiscoverBody(BaseModel):
    emailAddress: str = ""
    workspaceId: str = "default"


@router.post("/discover")
def mailbox_discover(body: DiscoverBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Resolve IMAP/SMTP settings from an email domain so the user never types a
    server. Returns discovered settings (kept hidden unless Advanced is opened)."""
    _require_enabled()
    return mail_setup.discover_mailbox(body.emailAddress)


@router.post("/test")
def mailbox_test(body: MailboxTestBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Non-destructive IMAP/SMTP probe. Never sends, never marks read, never
    persists credentials. Returns a specific error code on failure."""
    _require_enabled()
    return mail_setup.test_mailbox(session, body.workspaceId, body.model_dump())


@router.post("/connect")
def mailbox_connect(body: MailboxTestBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Probe and, only on success, persist the connection + store the secret by
    reference. Draft-and-approve send enforcement is unchanged."""
    _require_enabled()
    return mail_setup.connect_mailbox(session, body.workspaceId, body.model_dump())


@router.post("/disconnect")
def mailbox_disconnect(body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return mail_setup.disconnect(session, body.workspaceId)


@router.post("/reconnect")
def mailbox_reconnect(body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return mail_setup.reconnect(session, body.workspaceId)


@router.post("/oauth/{provider}/start")
def mailbox_oauth_start(provider: str, body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Honest OAuth start: only available when the deployment configured client
    credentials; otherwise it tells the UI to use IMAP/SMTP instead."""
    _require_enabled()
    out = mail_setup.oauth_start(session, body.workspaceId, provider)
    if out.get("reason") == "invalid_provider":
        raise HTTPException(status_code=400, detail=out.get("message", "Unknown email provider."))
    return out


@router.get("/oauth/{provider}/callback")
def mailbox_oauth_callback(provider: str, code: str = "", state: str = "",
                           error: str = "", session: Session = Depends(get_session)) -> Response:
    """OAuth redirect target: exchange the code, connect the mailbox, and send the
    browser back to DayPilot settings with a success/error code. Tokens are stored
    only server-side; nothing sensitive appears in the redirect URL."""
    _require_enabled()
    if error:
        return RedirectResponse(url=f"/#/settings/mail?email=error&reason={error}", status_code=303)
    out = mail_setup.oauth_callback(session, provider, code, state)
    if out.get("ok"):
        return RedirectResponse(url="/#/settings/mail?email=connected", status_code=303)
    return RedirectResponse(url=f"/#/settings/mail?email=error&reason={out.get('error', 'failed')}",
                            status_code=303)


@router.get("/messages/{uid}")
def message(uid: str, folder: str = "INBOX", workspaceId: str = "default",
            session: Session = Depends(get_session)) -> dict[str, Any]:
    """Fetch one real message/thread for the reading pane (read-only)."""
    _require_enabled()
    return email_service.message_detail(
        mail_setup.adapter_for_workspace(session, workspaceId), uid, folder=folder
    )


@router.post("/ai/revise")
def ai_revise(body: ReviseBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Revise the current real draft against an instruction (never sends)."""
    _require_enabled()
    return email_service.revise_reply(
        mail_setup.adapter_for_workspace(session, body.workspaceId),
        body.uid, body.current, body.instruction, body.tone,
    )


@router.get("/folders")
def folders(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return {"folders": mail_setup.adapter_for_workspace(session, workspaceId).list_folders()}


@router.get("/messages")
def messages(session: Session = Depends(get_session), workspaceId: str = "default", q: str | None = None) -> dict[str, Any]:
    _require_enabled()
    items = email_service.sync_inbox(session, mail_setup.adapter_for_workspace(session, workspaceId), workspaceId)
    if q:
        needle = q.lower()
        items = [i for i in items if needle in (i.get("subject", "") + " " + i.get("sender", "")).lower()]
    return {"items": items, "query": q}


@router.post("/messages/{uid}/draft-reply", status_code=201)
def draft_reply(uid: str, body: DraftReplyBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return email_service.draft_reply(
        session, mail_setup.adapter_for_workspace(session, body.workspaceId),
        body.workspaceId, uid, body.tone, body.signature,
    )


@router.post("/drafts/send")
def send(body: SendBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Send a draft. Requires an approved approval AND an explicit approval payload."""
    _require_enabled()
    try:
        return email_service.send_draft(
            session, mail_setup.adapter_for_workspace(session, body.workspaceId),
            body.workspaceId, body.draftUid,
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
