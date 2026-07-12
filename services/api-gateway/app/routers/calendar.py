from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.calendar import service as calendar_service

from ..db import get_session

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


class EventDraftBody(BaseModel):
    title: str
    startAt: str
    endAt: str
    workspaceId: str = "default"


@router.get("/events")
def events(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    return {
        "items": calendar_service.sync_events(session, workspaceId),
        "conflicts": calendar_service.detect_conflicts(session, workspaceId),
        "provider": calendar_service.calendar_provider(),
    }


@router.get("/conflicts")
def conflicts(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    calendar_service.sync_events(session, workspaceId)
    return {"conflicts": calendar_service.detect_conflicts(session, workspaceId)}


@router.post("/events/draft", status_code=201)
def draft_event(body: EventDraftBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return calendar_service.propose_event_draft(
        session, body.workspaceId, body.title, body.startAt, body.endAt
    )
