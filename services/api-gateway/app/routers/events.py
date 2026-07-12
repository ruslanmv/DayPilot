from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from .. import events as event_service
from ..db import get_session
from ..serializers import serialize_event

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.get("")
def list_events(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    afterSeq: int = 0,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    rows = event_service.list_events_since(
        session, workspace_id=workspaceId, after_seq=afterSeq, limit=limit
    )
    items = [serialize_event(e) for e in rows]
    return {
        "items": items,
        "lastSeq": items[-1]["seq"] if items else afterSeq,
        "types": sorted(event_service.EVENT_TYPES),
    }


@router.get("/stream")
async def stream_events(
    workspaceId: str = "default",
    lastSeq: int = 0,
) -> StreamingResponse:
    return StreamingResponse(
        event_service.event_stream(workspaceId, lastSeq),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
