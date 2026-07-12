from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import PlanBlock
from daypilot_orchestrator.continuity import continue_from_yesterday
from daypilot_orchestrator.plan_state import (
    InvalidPlanTransition,
    PlanState,
    allowed_actions,
)
from daypilot_orchestrator.today_engine import (
    build_or_get_draft,
    get_plan,
    start_focus,
    today_context,
    transition_plan,
)
from daypilot_orchestrator.wrapup import generate_wrapup

from ..db import get_session
from ..serializers import serialize_day_plan

router = APIRouter(prefix="/v1", tags=["plan"])


class TransitionBody(BaseModel):
    action: str
    summary: str | None = None


def _serialize_with_actions(session: Session, plan) -> dict[str, Any]:
    blocks = list(
        session.execute(select(PlanBlock).where(PlanBlock.day_plan_id == plan.id)).scalars()
    )
    payload = serialize_day_plan(plan, blocks)
    payload["allowedActions"] = [a.value for a in allowed_actions(plan.state)]
    return payload


@router.get("/today")
def get_today(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    return today_context(session, workspaceId)


@router.get("/plans/{plan_date}")
def read_plan(
    plan_date: str, session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    plan = get_plan(session, workspaceId, plan_date)
    if plan is None:
        raise HTTPException(status_code=404, detail="No plan for that date")
    return _serialize_with_actions(session, plan)


@router.post("/plans/{plan_date}/draft")
def draft_plan(
    plan_date: str, session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    """Create (or return) the DRAFT plan for a date, seeded from the day's tasks."""
    plan = build_or_get_draft(session, workspaceId, plan_date)
    return _serialize_with_actions(session, plan)


@router.post("/plans/{plan_date}/transition")
def transition(
    plan_date: str,
    body: TransitionBody,
    session: Session = Depends(get_session),
    workspaceId: str = "default",
) -> dict[str, Any]:
    try:
        plan = transition_plan(session, workspaceId, plan_date, body.action, body.summary)
    except InvalidPlanTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_with_actions(session, plan)


@router.get("/plans/{plan_date}/wrapup")
def wrapup(
    plan_date: str, session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    return generate_wrapup(session, workspaceId, plan_date)


@router.get("/continuity")
def continuity(
    session: Session = Depends(get_session), workspaceId: str = "default", limit: int = 20
) -> dict[str, Any]:
    return {"items": continue_from_yesterday(session, workspaceId, limit)}


@router.post("/focus/{task_id}")
def focus(
    task_id: str, session: Session = Depends(get_session), workspaceId: str = "default"
) -> dict[str, Any]:
    try:
        return start_focus(session, workspaceId, task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found") from None


@router.get("/plan-states")
def plan_states() -> dict[str, Any]:
    """Expose the lifecycle vocabulary for the UI."""
    return {"states": [s.value for s in PlanState]}
