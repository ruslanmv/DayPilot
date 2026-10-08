"""AI assistance for dmind maps (batch C1). Proposals only: nothing is saved or changed here."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from daypilot_orchestrator.assistant.orchestrator import active_connector
from daypilot_orchestrator.design import dmind_assist as ai
from daypilot_orchestrator.design.dmind_contract import validate_diagram

from .. import ai_credits as credits
from ..db import get_session
from ..rbac import ROLE_RANK
from .diagrams import access, access_role

router = APIRouter(prefix="/v1/diagrams/assist", tags=["diagrams"])


class AssistIn(BaseModel):
    action: str = Field(..., max_length=20)
    document: dict[str, Any] | None = None
    focus: list[str] = Field(default_factory=list, max_length=20)
    prompt: str = Field("", max_length=ai.MAX_PROMPT_CHARS)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    options: dict[str, Any] = Field(default_factory=dict)


def provider(session: Session, workspace: str):
    try:
        return active_connector(session, workspace)
    except Exception:  # noqa: BLE001 - a broken provider row must not break the editor
        return None


@router.get("/status")
def status(workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Whether AI actions can run; the editor uses this to explain rather than hide the buttons."""
    return {
        "available": provider(session, workspace) is not None,
        "actions": sorted(ai.ACTIONS),
        "credits": credits.summary(session, workspace),
    }


@router.get("/credits")
def credit_summary(workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    return credits.summary(session, workspace)


class GrantIn(BaseModel):
    amount: int = Field(0, ge=0, le=credits.MAX_GRANT)
    monthlyAllowance: int | None = Field(None, ge=0, le=credits.MAX_GRANT)


@router.post("/credits/grant")
def grant_credits(
    body: GrantIn, request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Owners add credits or set the monthly allowance. Disabled when credits are not turned on."""
    workspace, role = access_role(request, session)
    if ROLE_RANK.get(role, -1) < ROLE_RANK["owner"]:
        raise HTTPException(403, "only a workspace owner can add AI credits")
    if not credits.enabled():
        raise HTTPException(409, "AI credits are not turned on for this installation")
    credits.grant(session, workspace, body.amount, body.monthlyAllowance)
    return credits.summary(session, workspace)


@router.post("")
def assist(body: AssistIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    cost = credits.cost_for(body.action, len(body.focus)) if credits.enabled() else 0
    try:
        document = validate_diagram(body.document) if body.document is not None else None
        options = {k: v for k, v in body.options.items() if k in ("count", "mode", "language")}
        if isinstance(options.get("language"), str):
            options["language"] = options["language"][:40]
        connector = provider(session, workspace)
        if connector is not None and cost:
            # Taken before the model runs so concurrent requests cannot overspend. A failure below
            # rolls the whole request back (the charge with it); an offline answer is refunded.
            credits.charge(session, workspace, body.action, cost)
        result = ai.assist(connector, body.action, document, body.focus, body.prompt, body.history, options)
        if credits.enabled():
            if result.get("mode") == "offline" or connector is None:
                result["credits"] = {"charged": 0, "balance": credits.account(session, workspace).balance}
            else:
                result["credits"] = {"charged": cost, "balance": credits.account(session, workspace).balance}
        return result
    except ai.AssistError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:  # invalid map
        raise HTTPException(422, f"invalid diagram: {exc}") from exc
