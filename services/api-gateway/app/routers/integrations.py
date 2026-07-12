"""Integration Gateway API (batch I0/I1).

One ingress for connecting providers, inspecting capabilities, checking health,
and executing actions under the permission + approval model. Writes never
execute here — they open an approval; the caller performs them only after the
Approval Center grants the decision.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.integrations.provider import CapabilityNotFound, IntegrationError
from daypilot_orchestrator.integrations.service import (
    ActionBlocked,
    WriteNotApproved,
    available,
    capabilities,
    create_connection,
    disconnect_connection,
    execute_action,
    get_connection,
    list_connections,
    perform_pending_action,
    refresh_health,
)

from ..db import get_session

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


class ConnectBody(BaseModel):
    provider: str
    credentials: dict[str, Any] = {}
    workspaceId: str = "default"


class ExecuteBody(BaseModel):
    action: str
    input: Any = None


@router.get("")
def index(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return {"connections": list_connections(session, workspaceId), "available": available(workspaceId)}


@router.post("/connect", status_code=201)
def connect(body: ConnectBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return create_connection(session, body.workspaceId, body.provider, body.credentials)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{body.provider}'")
    except IntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{connection_id}")
def show(connection_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    conn = get_connection(session, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return conn


@router.get("/{connection_id}/capabilities")
def list_caps(connection_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return {"capabilities": capabilities(session, connection_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="connection not found")


@router.post("/{connection_id}/health")
def health(connection_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return refresh_health(session, connection_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="connection not found")


@router.post("/{connection_id}/disconnect")
def disconnect(connection_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return disconnect_connection(session, connection_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="connection not found")


@router.post("/{connection_id}/execute")
def execute(connection_id: str, body: ExecuteBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return execute_action(session, connection_id, body.action, body.input)
    except KeyError:
        raise HTTPException(status_code=404, detail="connection not found")
    except CapabilityNotFound:
        raise HTTPException(status_code=404, detail=f"unknown capability '{body.action}'")
    except ActionBlocked:
        raise HTTPException(status_code=403, detail="capability is blocked by policy")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/actions/{job_id}/perform")
def perform(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return perform_pending_action(session, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="action not found")
    except WriteNotApproved:
        raise HTTPException(status_code=409, detail="action not approved")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
