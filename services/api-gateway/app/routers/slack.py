"""HTTP surface for the Slack communication workspace.

Two rules shape this file:

* **Nothing here posts to Slack.** ``POST /drafts/{id}/send`` calls the
  orchestrator's ``send``, which calls the Integration Gateway's write path,
  which opens an Approval. The route returns ``approval_required``; the message
  goes out when a human decides it does.
* **Refinement proposes, it does not apply.** ``/refine`` returns a candidate and
  leaves the draft alone. ``/accept`` is the separate call the *Use this* button
  makes, and it records a revision so *Undo* works.

The feature is optional: with ``DAYPILOT_SLACK_WORKSPACE_ENABLED`` unset every
route except ``GET /status`` returns 404, and ``/status`` reports
``enabled: false`` so the UI can show a real state instead of guessing from a
missing route.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_knowledge.db import SlackConversation, SlackDraft, SlackMessage
from daypilot_orchestrator.calendar.connections import connected_providers
from daypilot_orchestrator.slack_workspace import service as slack_service
from daypilot_orchestrator.slack_workspace import settings as slack_settings
from daypilot_orchestrator.slack_workspace import transport as slack_transport

from ..db import get_session

router = APIRouter(prefix="/v1/slack", tags=["slack"])


def _require_enabled() -> None:
    if not slack_service.workspace_enabled():
        raise HTTPException(status_code=404, detail={
            "error": "slack_workspace_disabled",
            "message": "The Slack workspace is not enabled for this deployment.",
        })


def _draft(session: Session, draft_id: str) -> SlackDraft:
    row = session.get(SlackDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown draft '{draft_id}'")
    return row


def _conversation(session: Session, conversation_id: str) -> SlackConversation:
    row = session.get(SlackConversation, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown conversation '{conversation_id}'")
    return row


def _locked(exc: slack_service.DraftLocked) -> HTTPException:
    # 409 rather than 400: the request was well-formed, the draft simply moved on.
    return HTTPException(status_code=409, detail=str(exc))


# --- status & settings --------------------------------------------------------


@router.get("/status")
def status(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    """Reachable even when the feature is off — that is the point of it."""
    payload = slack_service.status(session, workspaceId)
    payload["delivery"] = slack_transport.describe()
    return payload


@router.get("/settings")
def read_settings(
    session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    _require_enabled()
    row = slack_settings.get_preferences(session, workspaceId)
    connected = connected_providers(session, workspaceId)
    return {
        "settings": slack_settings.serialize(row),
        # The catalogue is served, never hardcoded in the client: this list is a
        # permission, and a permission the browser invents is not a permission.
        "sources": [
            {
                "id": s["id"],
                "label": s["label"],
                "requires": s["requires"],
                "available": not s["requires"] or s["requires"] in connected,
                "alwaysOn": s["id"] in slack_settings.ALWAYS_ON_SOURCES,
            }
            for s in slack_settings.CONTEXT_SOURCES
        ],
        "effectiveSources": slack_settings.allowed_context_sources(
            session, workspaceId, connected
        ),
        "accessModes": list(slack_settings.ACCESS_MODES),
    }


class SettingsBody(BaseModel):
    """A partial update — only the keys present are applied."""

    model_config = {"extra": "allow"}


@router.put("/settings")
def write_settings(
    body: SettingsBody,
    session: Session = Depends(get_session),
    workspaceId: str = "default",
) -> dict[str, Any]:
    _require_enabled()
    try:
        row = slack_settings.update_preferences(session, workspaceId, body.model_dump())
    except slack_settings.InvalidSetting as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"settings": slack_settings.serialize(row)}


# --- inbox & conversations ----------------------------------------------------


@router.get("/inbox")
def inbox(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    group: str = "all",
) -> dict[str, Any]:
    _require_enabled()
    return {
        "items": slack_service.inbox(session, workspaceId, group),
        "counts": slack_service.inbox_counts(session, workspaceId),
        "group": group,
    }


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: str, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _require_enabled()
    return slack_service.thread(session, _conversation(session, conversation_id))


@router.get("/recipients")
def recipients(
    session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    _require_enabled()
    return {"items": slack_service.recipients(session, workspaceId)}


class HandledBody(BaseModel):
    handled: bool = True


@router.post("/messages/{message_id}/handled")
def set_handled(
    message_id: str, body: HandledBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _require_enabled()
    row = session.get(SlackMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown message '{message_id}'")
    return slack_service.serialize_message(
        slack_service.mark_handled(session, row, body.handled)
    )


# --- drafting -----------------------------------------------------------------


class DraftForBody(BaseModel):
    workspaceId: str = "default"
    messageId: str | None = None
    instruction: str = ""


@router.post("/conversations/{conversation_id}/draft", status_code=201)
def draft_reply(
    conversation_id: str, body: DraftForBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Prepare a reply on demand — the *Draft a reply* button.

    Exists because ``autoPrepare`` may be off, or the classifier may have decided
    this message did not need a draft and the user disagrees. Disagreeing with
    the classifier should cost one click, not a settings change.
    """
    _require_enabled()
    conversation = _conversation(session, conversation_id)
    message = session.get(SlackMessage, body.messageId) if body.messageId else None
    draft = slack_service.prepare_draft(
        session, body.workspaceId,
        conversation=conversation, message=message, instruction=body.instruction,
        connected_providers=connected_providers(session, body.workspaceId),
    )
    return slack_service.serialize_draft(draft)


class ComposeBody(BaseModel):
    workspaceId: str = "default"
    channelId: str = ""
    conversationId: str = ""
    kind: str = "im"
    name: str = ""
    counterpart: str = ""
    audience: str = "internal"
    instruction: str = ""


@router.post("/compose", status_code=201)
def compose(body: ComposeBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Start a new message — the *+ New message* button."""
    _require_enabled()
    if body.conversationId:
        conversation = _conversation(session, body.conversationId)
    elif body.channelId:
        conversation = slack_service.upsert_conversation(
            session, body.workspaceId, channel_id=body.channelId, kind=body.kind,
            name=body.name, counterpart=body.counterpart, audience=body.audience,
        )
    else:
        raise HTTPException(status_code=400, detail="a recipient is required")
    draft = slack_service.prepare_draft(
        session, body.workspaceId,
        conversation=conversation, message=None, instruction=body.instruction,
        connected_providers=connected_providers(session, body.workspaceId),
    )
    return {
        "conversation": slack_service.serialize_conversation(conversation),
        "draft": slack_service.serialize_draft(draft),
    }


@router.get("/drafts/{draft_id}")
def read_draft(draft_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    return slack_service.serialize_draft(_draft(session, draft_id))


class TextBody(BaseModel):
    text: str


@router.patch("/drafts/{draft_id}")
def edit_draft(
    draft_id: str, body: TextBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    _require_enabled()
    try:
        row = slack_service.update_text(session, _draft(session, draft_id), body.text)
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    return slack_service.serialize_draft(row)


class TransformBody(BaseModel):
    kind: str


@router.post("/drafts/{draft_id}/transform")
def transform_draft(
    draft_id: str, body: TransformBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """One of the four quick rewrites: shorter · direct · detailed · friendly."""
    _require_enabled()
    try:
        row = slack_service.apply_transform(session, _draft(session, draft_id), body.kind)
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return slack_service.serialize_draft(row)


class RefineBody(BaseModel):
    instruction: str


@router.post("/drafts/{draft_id}/refine")
def refine_draft(
    draft_id: str, body: RefineBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Return a proposal. **Does not change the draft.**

    The assistant panel renders this as *[Use this] [Insert] [Try again]*. If
    this route mutated, the user would have to undo an edit they never chose,
    and every experiment would carry a cost.
    """
    _require_enabled()
    try:
        return slack_service.propose_refinement(_draft(session, draft_id), body.instruction)
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc


class AcceptBody(BaseModel):
    text: str
    instruction: str = ""


@router.post("/drafts/{draft_id}/accept")
def accept_draft(
    draft_id: str, body: AcceptBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """*Use this* — apply a proposal, keeping the old text as a revision."""
    _require_enabled()
    try:
        row = slack_service.accept_refinement(
            session, _draft(session, draft_id), body.text, body.instruction
        )
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    return slack_service.serialize_draft(row)


@router.post("/drafts/{draft_id}/undo")
def undo_draft(draft_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    try:
        row = slack_service.undo(session, _draft(session, draft_id))
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    return slack_service.serialize_draft(row)


class SendBody(BaseModel):
    workspaceId: str = "default"


@router.post("/drafts/{draft_id}/send")
def send_draft(
    draft_id: str, body: SendBody, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Request delivery. Returns ``approval_required``; does not post.

    The response deliberately carries ``approvalId`` rather than a Slack message
    timestamp, because at this point there is no Slack message — only a pending
    decision in the Approval Center.
    """
    _require_enabled()
    try:
        return slack_service.send(session, body.workspaceId, _draft(session, draft_id))
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    except slack_service.NotConnected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/drafts/{draft_id}")
def discard_draft(draft_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_enabled()
    try:
        row = slack_service.discard(session, _draft(session, draft_id))
    except slack_service.DraftLocked as exc:
        raise _locked(exc) from exc
    return slack_service.serialize_draft(row)


# --- inbound events -----------------------------------------------------------


@router.post("/events")
async def events(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    """The Events API request URL, for deployments not using Socket Mode.

    Signature verification runs on the raw body before the payload is parsed for
    meaning — an unverified request is not an event, it is a stranger's POST.
    """
    _require_enabled()
    body = await request.body()
    try:
        slack_transport.verify_signature(body, dict(request.headers))
    except slack_transport.UntrustedEvent as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    envelope = await request.json()
    if slack_transport.is_url_verification(envelope):
        return {"challenge": str(envelope.get("challenge", ""))}

    normalized = slack_transport.normalize(envelope)
    if normalized is None:
        # Acknowledged, deliberately ignored. Slack retries anything that is not
        # a 2xx, and retrying a channel-join forever helps nobody.
        return {"status": "ignored"}

    workspace_id = str(envelope.get("workspaceId") or "default")
    return slack_service.ingest(
        session, workspace_id, normalized,
        connected_providers=connected_providers(session, workspace_id),
    )
