"""Unified notification center + cross-integration workflows (batch I6/I8)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.integrations.notifications import (
    list_notifications,
    summary,
)
from daypilot_orchestrator.integrations.workflows import available_workflows, run_workflow

from ..db import get_session

router = APIRouter(prefix="/v1", tags=["integrations", "notifications"])


@router.get("/notifications")
def notifications(workspaceId: str = "default", severity: str | None = None,
                  session: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        "notifications": list_notifications(session, workspaceId, severity=severity),
        "summary": summary(session, workspaceId),
    }


@router.get("/notifications/summary")
def notifications_summary(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, int]:
    return summary(session, workspaceId)


class RunWorkflowBody(BaseModel):
    event: dict[str, Any] = {}
    workspaceId: str = "default"


@router.get("/workflows")
def workflows() -> dict[str, Any]:
    return {"workflows": available_workflows()}


@router.post("/workflows/{workflow_id}/run")
def run(workflow_id: str, body: RunWorkflowBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    event = {**body.event, "workspaceId": body.workspaceId}
    try:
        return run_workflow(session, workflow_id, event)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown workflow '{workflow_id}'")
