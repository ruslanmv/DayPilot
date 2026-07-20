from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_models.provider_health import provider_health
from daypilot_models.routing import route_for_role, serialize_routes

from .. import providers_platform as pp
from ..db import get_session

router = APIRouter(prefix="/v1/providers", tags=["providers"])


class LocalTestBody(BaseModel):
    workspaceId: str = "default"
    baseUrl: str
    apiKey: str | None = None


class CloudLoginBody(BaseModel):
    workspaceId: str = "default"
    email: str
    password: str


class ActiveBody(BaseModel):
    workspaceId: str = "default"
    kind: str  # local | ollabridge_cloud


class DefaultModelBody(BaseModel):
    workspaceId: str = "default"
    kind: str
    model: str


class WsBody(BaseModel):
    workspaceId: str = "default"


@router.get("/status")
def provider_status(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """Backend-owned provider state (the browser never fabricates it)."""
    return pp.status(session, workspaceId)


@router.post("/local/discover")
def local_discover(body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    from daypilot_models.ollabridge_client import LOCAL_DEFAULT_URL
    return pp.local_test(session, body.workspaceId, LOCAL_DEFAULT_URL, None)


@router.post("/local/test")
def local_test(body: LocalTestBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.local_test(session, body.workspaceId, body.baseUrl, body.apiKey)


@router.post("/local/connect")
def local_connect(body: LocalTestBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.local_connect(session, body.workspaceId, body.baseUrl, body.apiKey)


@router.post("/cloud/login")
def cloud_login(body: CloudLoginBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.cloud_login(session, body.workspaceId, body.email, body.password)


@router.get("/cloud/models")
def cloud_models(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.cloud_models(session, workspaceId)


@router.post("/cloud/logout")
def cloud_logout(body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.cloud_logout(session, body.workspaceId)


@router.patch("/active")
def set_active(body: ActiveBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return pp.set_active(session, body.workspaceId, body.kind)
    except PermissionError:
        raise HTTPException(status_code=409, detail="provider_not_connected")
    except ValueError:
        raise HTTPException(status_code=400, detail="unknown_provider")


@router.patch("/default-model")
def set_default_model(body: DefaultModelBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return pp.set_default_model(session, body.workspaceId, body.kind, body.model)


@router.get("/health")
def health() -> dict[str, Any]:
    """Ollabridge provider health: status, latency, models, routes, fallback."""
    return provider_health()


@router.get("/routes")
def routes() -> dict[str, Any]:
    return {"routes": serialize_routes()}


@router.get("/route/{role}")
def route(role: str) -> dict[str, Any]:
    policy = route_for_role(role)
    return {
        "role": policy.role,
        "model": policy.preferred_model,
        "tier": policy.tier,
        "latencyBudgetMs": policy.latency_budget_ms,
        "fallback": list(policy.fallback),
    }
