"""MCP server governance API (batch I4/I5).

Attach remote/local MCP servers, inspect and enable tools, override
classification, and execute tools under the policy + approval layer. Writes
open an approval; the caller performs them only after it is granted.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.integrations.mcp.service import (
    ToolBlocked,
    ToolNotEnabled,
    WriteNotApproved,
    add_server,
    execute_tool,
    list_servers,
    list_tools,
    override_classification,
    perform_pending_tool,
    set_tool_enabled,
)

from ..db import get_session

router = APIRouter(prefix="/v1/integrations/mcp", tags=["integrations", "mcp"])


class AddServerBody(BaseModel):
    name: str
    transport: str = "streamable_http"  # stdio | streamable_http
    endpoint: str | None = None
    command: str | None = None
    workspaceId: str = "default"


class EnableBody(BaseModel):
    enabled: bool = True


class ClassifyBody(BaseModel):
    kind: str  # read | write | destructive


class ExecuteToolBody(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}


@router.get("")
def servers(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return {"servers": list_servers(session, workspaceId)}


@router.post("/add", status_code=201)
def add(body: AddServerBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return add_server(session, body.workspaceId, body.name, body.transport, body.endpoint, body.command)


@router.get("/{connection_id}/tools")
def tools(connection_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return {"tools": list_tools(session, connection_id)}
    except KeyError:
        raise HTTPException(status_code=404, detail="server not found")


@router.post("/{connection_id}/tools/{tool}/enable")
def enable(connection_id: str, tool: str, body: EnableBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return set_tool_enabled(session, connection_id, tool, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail="server or tool not found")


@router.post("/{connection_id}/tools/{tool}/classify")
def classify(connection_id: str, tool: str, body: ClassifyBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return override_classification(session, connection_id, tool, body.kind)
    except KeyError:
        raise HTTPException(status_code=404, detail="server not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid kind")


@router.post("/{connection_id}/execute")
def execute(connection_id: str, body: ExecuteToolBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return execute_tool(session, connection_id, body.tool, body.arguments)
    except KeyError:
        raise HTTPException(status_code=404, detail="server not found")
    except ToolNotEnabled:
        raise HTTPException(status_code=403, detail="tool is not enabled")
    except ToolBlocked:
        raise HTTPException(status_code=403, detail="tool is blocked by policy")


@router.post("/actions/{job_id}/perform")
def perform(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return perform_pending_tool(session, job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="action not found")
    except WriteNotApproved:
        raise HTTPException(status_code=409, detail="action not approved")
