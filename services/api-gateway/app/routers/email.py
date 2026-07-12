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


@router.get("/status")
def status() -> dict[str, Any]:
    """Always reachable so the UI can show/hide the tab without a 404 storm."""
    return {"enabled": email_enabled()}


@router.get("/folders")
def folders() -> dict[str, Any]:
    _require_enabled()
    return {"folders": get_adapter().list_folders()}


@router.get("/messages")
def messages(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    _require_enabled()
    items = email_service.sync_inbox(session, get_adapter(), workspaceId)
    return {"items": items}


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
