"""AI assistance for dmind maps (batch C1). Proposals only: nothing is saved or changed here."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from daypilot_orchestrator.assistant.orchestrator import active_connector
from daypilot_orchestrator.design import dmind_assist as ai
from daypilot_orchestrator.design.dmind_contract import validate_diagram

from ..db import get_session
from .diagrams import access

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
    return {"available": provider(session, workspace) is not None, "actions": sorted(ai.ACTIONS)}


@router.post("")
def assist(body: AssistIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        document = validate_diagram(body.document) if body.document is not None else None
        options = {k: v for k, v in body.options.items() if k in ("count", "mode", "language")}
        if isinstance(options.get("language"), str):
            options["language"] = options["language"][:40]
        return ai.assist(
            provider(session, workspace), body.action, document, body.focus, body.prompt, body.history, options
        )
    except ai.AssistError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:  # invalid map
        raise HTTPException(422, f"invalid diagram: {exc}") from exc
