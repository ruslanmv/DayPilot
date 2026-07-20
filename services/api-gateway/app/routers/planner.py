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
from daypilot_orchestrator.planner.service import chat_with_plan, generate_plan, planner_readiness, read_plan
from daypilot_orchestrator.planner.sync import apply_proposal, daily_review, discard_proposal, sync_plan

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


class SyncBody(BaseModel):
    workspaceId: str = "default"
    now: str | None = None  # HH:MM override for tests; defaults to wall clock


class ProposalApplyBody(BaseModel):
    proposalId: str
    instruction: str
    workspaceId: str = "default"


class ProposalDiscardBody(BaseModel):
    proposalId: str
    signature: str
    reason: str = "user_already_working"
    workspaceId: str = "default"


@router.get("/plans/{plan_date}/readiness")
def readiness(plan_date: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """Real readiness/source counts driving the automatic Planning experience."""
    return planner_readiness(session, workspaceId, plan_date)


@router.post("/plans/{plan_date}/sync")
def sync(plan_date: str, body: SyncBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """One smart-sync pass: minor status updates applied, new work proposed."""
    return sync_plan(session, body.workspaceId, plan_date, now=body.now)


@router.post("/plans/{plan_date}/daily-review")
def review_day(plan_date: str, body: SyncBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Start-of-day review: reconcile statuses; auto-build the plan when ready."""
    return daily_review(session, body.workspaceId, plan_date, now=body.now)


@router.post("/plans/{plan_date}/proposal/apply")
def proposal_apply(plan_date: str, body: ProposalApplyBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return apply_proposal(session, body.workspaceId, plan_date, body.proposalId, body.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/plans/{plan_date}/proposal/discard")
def proposal_discard(plan_date: str, body: ProposalDiscardBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return discard_proposal(session, body.workspaceId, plan_date, body.proposalId, body.signature, body.reason)


@router.get("/plans/{plan_date}")
def read(plan_date: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return read_plan(session, workspaceId, plan_date)


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
