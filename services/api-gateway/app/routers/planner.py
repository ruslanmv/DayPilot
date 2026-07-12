"""Multi-agent day-planner API.

Generate/replan an optimized day, chat with the plan, and run the governed
self-optimization loop (review → approval → apply new config version).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.planner.revision import active_config, apply_config, review_planner
from daypilot_orchestrator.planner.service import chat_with_plan, generate_plan

from ..db import get_session

router = APIRouter(prefix="/v1/planner", tags=["planner"])


class PlanBody(BaseModel):
    workspaceId: str = "default"
    instruction: str | None = None


class ChatBody(BaseModel):
    message: str
    workspaceId: str = "default"


class ApplyBody(BaseModel):
    approvalId: str
    proposed: dict[str, Any]
    workspaceId: str = "default"


@router.post("/plans/{plan_date}/generate")
def generate(plan_date: str, body: PlanBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return generate_plan(session, body.workspaceId, plan_date, instruction=body.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/plans/{plan_date}/chat")
def chat(plan_date: str, body: ChatBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return chat_with_plan(session, body.workspaceId, plan_date, body.message)


@router.get("/config")
def config(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return {"config": active_config(session, workspaceId).as_dict()}


@router.post("/review")
def review(body: PlanBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return review_planner(session, body.workspaceId)


@router.post("/config/apply")
def apply(body: ApplyBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return apply_config(session, body.workspaceId, body.approvalId, body.proposed)
    except KeyError:
        raise HTTPException(status_code=404, detail="approval not found")
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
