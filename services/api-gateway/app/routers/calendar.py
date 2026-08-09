from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.calendar import connections as calendar_connections
from daypilot_orchestrator.calendar import service as calendar_service
from daypilot_orchestrator.calendar import settings as calendar_settings

from .. import calendar_oauth
from ..db import get_session

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


class EventDraftBody(BaseModel):
    title: str
    startAt: str
    endAt: str
    workspaceId: str = "default"


class SettingsBody(BaseModel):
    """A partial update — only the keys present are applied."""

    model_config = {"extra": "allow"}


@router.get("/events")
def events(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    """Read the local event store.

    This used to call ``sync_events()``, which made rendering the calendar
    perform a write and put a provider round-trip on a read path. Syncing is now
    ``POST /v1/calendar/sync`` and belongs to the job queue.
    """
    return {
        "items": calendar_service.list_events(session, workspaceId),
        "conflicts": calendar_service.detect_conflicts(session, workspaceId),
        "provider": calendar_service.calendar_provider(),
    }


@router.get("/conflicts")
def conflicts(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    return {"conflicts": calendar_service.detect_conflicts(session, workspaceId)}


@router.post("/events/draft", status_code=201)
def draft_event(body: EventDraftBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return calendar_service.propose_event_draft(
        session, body.workspaceId, body.title, body.startAt, body.endAt
    )


# ---- connection status + behaviour -------------------------------------------


@router.get("/status")
def calendar_status(
    session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    """Which calendars are connected and how fresh they are.

    The Calendar header and the planner read the same answer, so the chip in the
    corner and the plan below it can never disagree about whether a calendar was
    actually consulted.
    """
    return calendar_connections.status(session, workspaceId)


@router.get("/settings")
def read_settings(
    session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    row = calendar_settings.get_settings(session, workspaceId)
    connected = calendar_connections.connected_providers(session, workspaceId)
    return {
        "settings": calendar_settings.serialize(row),
        # The catalogue travels with the settings so the UI never hardcodes a
        # source list that could drift from what the server will honour.
        "sources": [
            {
                "id": s["id"],
                "label": s["label"],
                "requires": s["requires"],
                "available": not s["requires"] or s["requires"] in connected,
                "alwaysOn": s["id"] in calendar_settings.ALWAYS_ON_SOURCES,
            }
            for s in calendar_settings.CONTEXT_SOURCES
        ],
        "effectiveSources": calendar_settings.allowed_context_sources(
            session, workspaceId, connected
        ),
    }


@router.put("/settings")
def write_settings(
    body: SettingsBody,
    session: Session = Depends(get_session),
    workspaceId: str = "default",
) -> dict[str, Any]:
    try:
        row = calendar_settings.update_settings(session, workspaceId, body.model_dump())
    except calendar_settings.InvalidSetting as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"settings": calendar_settings.serialize(row)}


# ---- connecting a calendar ---------------------------------------------------


@router.get("/providers")
def providers() -> dict[str, Any]:
    """Which calendar providers this deployment can actually offer.

    A provider with no OAuth client configured is reported unavailable rather
    than shown as a button that dead-ends at the identity provider.
    """
    return {
        "items": [
            {
                "provider": p,
                "label": cfg["label"],
                "configured": calendar_oauth.is_configured(p),
                "scopes": cfg["scope"].split(),
                "readOnly": True,
            }
            for p, cfg in calendar_oauth.PROVIDERS.items()
        ]
    }


@router.post("/connect/{provider}")
def connect(provider: str, workspaceId: str = "default", returnTo: str = "") -> dict[str, Any]:
    """Begin the authorization-code flow; returns the URL to send the user to."""
    key = calendar_oauth.normalize_provider(provider)
    if key is None:
        raise HTTPException(status_code=404, detail=f"unknown calendar provider '{provider}'")
    return calendar_oauth.build_authorization(workspaceId, key, returnTo or None)


@router.get("/callback")
def callback(
    code: str = "", state: str = "", session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Finish the flow: exchange the code and record the connection."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code or state")
    try:
        return calendar_oauth.handle_callback(session, code, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
def sync(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    """Refresh the local event store from the connected calendars.

    Deliberately a POST of its own: reading ``GET /events`` used to perform this
    upsert as a side effect, which made rendering the calendar a write.
    """
    items = calendar_service.sync_events(session, workspaceId)
    return {
        "synced": len(items),
        "status": calendar_connections.status(session, workspaceId),
    }
