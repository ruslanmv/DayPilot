from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.assistant import orchestrator

from ..db import get_session

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


class TurnBody(BaseModel):
    message: str
    workspaceId: str = "default"
    sessionId: str | None = None


@router.post("/turn")
def turn(body: TurnBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Run one assistant turn. The backend classifies the intent, invokes only
    invokable (read-only / controlled-local-write) tools against the real
    services, and returns a deterministic reply + optional UI action. It never
    sends email or calls a provider directly."""
    return orchestrator.run_turn(session, body.workspaceId, body.message, body.sessionId)


@router.get("/tools")
def tools() -> dict[str, Any]:
    """The registered assistant tools and their risk classes (transparency)."""
    return {"tools": orchestrator.tool_catalog()}


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = orchestrator.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run


@router.get("/runs/{run_id}/events")
def get_events(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    if orchestrator.get_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return {"events": orchestrator.get_events(session, run_id)}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = orchestrator.cancel_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return run
