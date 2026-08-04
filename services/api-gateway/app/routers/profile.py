"""AI profile, goals, and onboarding API (Phase 1).

Ownership is always derived from the authenticated session (or a well-defined
local owner when session enforcement is off) — never from a client-supplied id.
Cookie-authenticated writes must echo the CSRF token. Profile writes use the
``If-Match``/revision optimistic-concurrency contract; a stale revision returns
``409 profile_revision_conflict`` with the current server value.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from .. import profile_platform as pp
from ..db import get_session
from ..profile_schemas import GoalCreate, GoalUpdate, ProfileUpdate

router = APIRouter(prefix="/v1/profile", tags=["profile"])
onboarding_router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


def _require_session() -> bool:
    return os.getenv("DAYPILOT_REQUIRE_SESSION", "false").lower() == "true"


def get_owner(
    session: Session = Depends(get_session),
    dp_session: Optional[str] = Cookie(default=None),
) -> pp.Owner:
    try:
        return pp.resolve_owner(session, dp_session, _require_session())
    except PermissionError:
        raise HTTPException(status_code=401, detail="not_authenticated")


def require_csrf(owner: pp.Owner, x_csrf_token: Optional[str]) -> None:
    """Enforce double-submit CSRF for real cookie sessions. In local mode there
    is no session token, so there is nothing to forge — the write is allowed."""
    if owner.csrf_token is None:
        return
    if not x_csrf_token or x_csrf_token != owner.csrf_token:
        raise HTTPException(status_code=403, detail="csrf_failed")


def _validation_400(exc: ValidationError):
    return HTTPException(status_code=422, detail={
        "code": "invalid_profile",
        "errors": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()],
    })


# --- AI profile --------------------------------------------------------------

@router.get("/ai")
def get_ai_profile(
    response: Response,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    data = pp.serialize_profile(pp._get_profile(session, owner))
    response.headers["ETag"] = f'"{data["revision"]}"'
    return data


def _write_profile(session, owner, payload, if_match, x_csrf_token):
    require_csrf(owner, x_csrf_token)
    try:
        update = ProfileUpdate.model_validate(payload)
    except ValidationError as exc:
        raise _validation_400(exc)
    try:
        return pp.apply_profile_update(session, owner, update, if_match)
    except pp.ProfileConflict as conflict:
        raise HTTPException(status_code=409, detail={
            "code": "profile_revision_conflict",
            "revision": conflict.revision,
            "current": conflict.current,
        })


@router.put("/ai")
def put_ai_profile(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    return _write_profile(session, owner, payload, if_match, x_csrf_token)


@router.patch("/ai")
def patch_ai_profile(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    return _write_profile(session, owner, payload, if_match, x_csrf_token)


@router.delete("/ai/learned")
def reset_learned(
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    return pp.reset_learned(session, owner)


@router.get("/ai/observations")
def list_observations(
    state: Optional[str] = None,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    return pp.list_observations(session, owner, state)


class ObservationBody(BaseModel):
    category: str
    value: dict[str, Any] = Field(default_factory=dict)
    sourceType: str = "inferred"
    confidence: float = 0.5
    ttlDays: Optional[int] = 90


@router.post("/ai/observations", status_code=201)
def record_observation(
    body: ObservationBody,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    out = pp.record_observation(
        session, owner, body.category, body.value,
        source_type=body.sourceType, confidence=body.confidence, ttl_days=body.ttlDays,
    )
    if out is None:
        # Suppressed (duplicate/previously rejected) or unknown category — honest,
        # not an error: nothing new was recorded.
        return {"recorded": False}
    return {"recorded": True, "observation": out}


@router.post("/ai/observations/{obs_id}/confirm")
def confirm_observation(
    obs_id: str,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    out = pp.decide_observation(session, owner, obs_id, "confirm")
    if out is None:
        raise HTTPException(status_code=404, detail="observation_not_found")
    return out


@router.post("/ai/observations/{obs_id}/reject")
def reject_observation(
    obs_id: str,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    out = pp.decide_observation(session, owner, obs_id, "reject")
    if out is None:
        raise HTTPException(status_code=404, detail="observation_not_found")
    return out


@router.get("/ai/export")
def export_ai_profile(
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    return pp.export_profile(session, owner)


_PREVIEW_PURPOSES = {"planning", "drafting", "knowledge", "agent_delegation", "assistant"}


@router.get("/ai/context-preview")
def context_preview(
    purpose: str = "planning",
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    """The EXACT typed projection the assistant/planner would receive for this
    purpose — so 'What AI sees' is the real thing, not a UI approximation. Runs
    the same ProfileContextBuilder the orchestrator uses."""
    if purpose not in _PREVIEW_PURPOSES:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_purpose", "allowed": sorted(_PREVIEW_PURPOSES)})
    try:
        from daypilot_orchestrator.profile.context_builder import build_projection
    except Exception:  # noqa: BLE001
        return {"purpose": purpose, "profileRevision": 0, "includedCategories": [], "provenance": {}}
    proj = build_projection(
        session, workspace_id=owner.workspace_id, user_id=owner.user_id, purpose=purpose,
    )
    return proj.to_dict()


class LegacyImportBody(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


@router.post("/ai/import-legacy")
def import_legacy(
    body: LegacyImportBody,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    # Never trust free-form values as credentials — the service allowlists keys.
    return pp.import_legacy(session, owner, body.fields or {})


# --- goals -------------------------------------------------------------------

@router.get("/goals")
def get_goals(
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    return pp.list_goals(session, owner)


@router.post("/goals", status_code=201)
def post_goal(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    try:
        body = GoalCreate.model_validate(payload)
    except ValidationError as exc:
        raise _validation_400(exc)
    return pp.create_goal(session, owner, body)


@router.patch("/goals/{goal_id}")
def patch_goal(
    goal_id: str,
    payload: dict[str, Any],
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    try:
        body = GoalUpdate.model_validate(payload)
    except ValidationError as exc:
        raise _validation_400(exc)
    out = pp.update_goal(session, owner, goal_id, body)
    if out is None:
        raise HTTPException(status_code=404, detail="goal_not_found")
    return out


@router.delete("/goals/{goal_id}", status_code=204)
def remove_goal(
    goal_id: str,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> None:
    require_csrf(owner, x_csrf_token)
    if not pp.delete_goal(session, owner, goal_id):
        raise HTTPException(status_code=404, detail="goal_not_found")


# --- onboarding --------------------------------------------------------------

@onboarding_router.get("")
def get_onboarding(
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
) -> dict[str, Any]:
    return pp.onboarding_view(session, owner)


class OnboardingPatchBody(BaseModel):
    currentStep: Optional[str] = None
    completedSteps: Optional[list[str]] = None
    dismissed: Optional[bool] = None


@onboarding_router.patch("")
def patch_onboarding(
    body: OnboardingPatchBody,
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    return pp.patch_onboarding(
        session, owner,
        current_step=body.currentStep,
        completed_steps=body.completedSteps,
        dismissed=body.dismissed,
    )


@onboarding_router.post("/complete")
def complete_onboarding(
    session: Session = Depends(get_session),
    owner: pp.Owner = Depends(get_owner),
    x_csrf_token: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    require_csrf(owner, x_csrf_token)
    try:
        return pp.complete_onboarding(session, owner)
    except pp.ProfileValidation as exc:
        raise HTTPException(status_code=422, detail={
            "code": "required_fields_missing", "missing": exc.missing,
        })
