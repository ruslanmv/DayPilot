"""MCP tool governance service (batch I4/I5).

Attach remote/local MCP servers, discover and classify their tools, enable
selected ones, and execute them under DayPilot's policy layer. The required
security path is enforced here:

    AI request -> tool router -> policy check -> approval check -> MCP client -> server

The model can only ask for a tool; it never receives an MCP client. Reads run
immediately; writes/destructive tools open an approval and a durable job.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, Event, Job, MCPConnection

from ..permissions import RISK_BY_KIND, Permission, resolve_permission
from ..provider import CapabilityKind
from .classification import classify_tool
from .client import MCPClient, StdioClient, StreamableHttpClient


class ToolNotEnabled(PermissionError):
    pass


class ToolBlocked(PermissionError):
    pass


class WriteNotApproved(PermissionError):
    pass


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _audit(session: Session, event_type: str, risk: str, decision: str, payload: dict[str, Any]) -> None:
    session.add(AuditLog(event_type=event_type, risk=risk, decision=decision, payload_json=payload))


def client_for(conn: MCPConnection, injected: MCPClient | None = None) -> MCPClient:
    if injected is not None:
        return injected
    if conn.transport == "streamable_http":
        return StreamableHttpClient(conn.endpoint or "")
    return StdioClient(conn.command or "")


def _kind_of(conn: MCPConnection, tool: str) -> CapabilityKind:
    override = (conn.overrides_json or {}).get(tool)
    if override:
        try:
            return CapabilityKind(override)
        except ValueError:
            pass
    for t in conn.tools_json or []:
        if t.get("name") == tool:
            return CapabilityKind(t.get("kind", "write"))
    return CapabilityKind.WRITE


def _serialize(conn: MCPConnection) -> dict[str, Any]:
    return {
        "id": conn.id,
        "workspaceId": conn.workspace_id,
        "name": conn.name,
        "transport": conn.transport,
        "endpoint": conn.endpoint,
        "command": conn.command,
        "status": conn.status,
        "enabledTools": list(conn.enabled_tools or []),
    }


def add_server(
    session: Session,
    workspace_id: str,
    name: str,
    transport: str,
    endpoint: str | None = None,
    command: str | None = None,
    *,
    client: MCPClient | None = None,
) -> dict[str, Any]:
    """Attach an MCP server: discover and classify its tools. Tools start
    disabled (opt-in)."""
    conn = MCPConnection(
        workspace_id=workspace_id, name=name, transport=transport,
        endpoint=endpoint, command=command, status="connected",
    )
    session.add(conn)
    session.flush()
    resolved = client or client_for(conn)
    try:
        discovered = resolved.list_tools()
        conn.tools_json = [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "kind": classify_tool(t["name"], t.get("annotations")).value,
            }
            for t in discovered
        ]
        conn.status = "connected"
    except Exception as exc:  # noqa: BLE001 - surfaced as unavailable, not raised
        conn.status = "unavailable"
        conn.detail = str(exc)[:500]
    _audit(session, "mcp.attached", "low", "recorded",
           {"connectionId": conn.id, "name": name, "transport": transport, "tools": len(conn.tools_json)})
    _emit(session, workspace_id, "mcp.attached", {"connectionId": conn.id, "name": name, "status": conn.status})
    session.flush()
    return _serialize(conn)


def list_servers(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    rows = session.execute(
        select(MCPConnection).where(MCPConnection.workspace_id == workspace_id)
    ).scalars()
    return [_serialize(c) for c in rows]


def list_tools(session: Session, connection_id: str) -> list[dict[str, Any]]:
    conn = _require(session, connection_id)
    enabled = set(conn.enabled_tools or [])
    out = []
    for t in conn.tools_json or []:
        kind = _kind_of(conn, t["name"])
        perm = resolve_permission(kind, None, t["name"])
        out.append({
            "name": t["name"], "description": t.get("description", ""),
            "kind": kind.value, "enabled": t["name"] in enabled, "permission": perm.value,
        })
    return out


def set_tool_enabled(session: Session, connection_id: str, tool: str, enabled: bool) -> dict[str, Any]:
    conn = _require(session, connection_id)
    known = {t["name"] for t in conn.tools_json or []}
    if tool not in known:
        raise KeyError(tool)
    current = set(conn.enabled_tools or [])
    if enabled:
        current.add(tool)
    else:
        current.discard(tool)
    conn.enabled_tools = sorted(current)
    _audit(session, "mcp.tool.enabled" if enabled else "mcp.tool.disabled", "low", "recorded",
           {"connectionId": conn.id, "tool": tool})
    session.flush()
    return _serialize(conn)


def override_classification(session: Session, connection_id: str, tool: str, kind: str) -> dict[str, Any]:
    conn = _require(session, connection_id)
    CapabilityKind(kind)  # validate
    overrides = dict(conn.overrides_json or {})
    overrides[tool] = kind
    conn.overrides_json = overrides
    _audit(session, "mcp.tool.reclassified", "low", "recorded",
           {"connectionId": conn.id, "tool": tool, "kind": kind})
    session.flush()
    return {"tool": tool, "kind": kind}


def execute_tool(
    session: Session,
    connection_id: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    client: MCPClient | None = None,
) -> dict[str, Any]:
    """Router + policy check. Reads run now; writes/destructive open an approval
    and a durable job. The model never bypasses this path."""
    conn = _require(session, connection_id)
    if tool not in set(conn.enabled_tools or []):
        raise ToolNotEnabled(tool)
    kind = _kind_of(conn, tool)
    perm = resolve_permission(kind, None, tool)
    risk = RISK_BY_KIND.get(kind, "medium")

    if perm is Permission.BLOCKED:
        _audit(session, "mcp.blocked", risk, "blocked", {"connectionId": conn.id, "tool": tool})
        raise ToolBlocked(tool)

    if perm is Permission.ALLOWED:
        resolved = client_for(conn, client)
        result = resolved.call_tool(tool, arguments or {})
        conn.updated_at = datetime.utcnow()
        _audit(session, "mcp.read.executed", risk, "executed", {"connectionId": conn.id, "tool": tool})
        _emit(session, conn.workspace_id, "mcp.tool_executed", {"connectionId": conn.id, "tool": tool, "kind": kind.value})
        session.flush()
        return {"status": "executed", "tool": tool, "result": result}

    # Write/destructive — enqueue a durable job and open an approval.
    job = Job(
        workspace_id=conn.workspace_id, kind="mcp.execute", state="blocked_on_approval",
        payload_json={"connectionId": conn.id, "tool": tool, "arguments": arguments or {}},
    )
    session.add(job)
    session.flush()
    approval = Approval(
        workspace_id=conn.workspace_id, action=f"mcp.{tool}",
        summary=f"Run MCP tool {tool} on {conn.name}", risk=risk, status="pending",
        resource_type="mcp_tool", resource_id=job.id,
    )
    session.add(approval)
    _audit(session, "mcp.write.requested", risk, "recorded",
           {"connectionId": conn.id, "tool": tool, "jobId": job.id, "approvalId": approval.id})
    _emit(session, conn.workspace_id, "approval.requested",
          {"resourceType": "mcp_tool", "resourceId": job.id, "tool": tool})
    session.flush()
    return {"status": "approval_required", "tool": tool, "approvalId": approval.id, "jobId": job.id}


def perform_pending_tool(session: Session, job_id: str, *, client: MCPClient | None = None) -> dict[str, Any]:
    """Run an approved MCP tool. Refuses unless the linked approval is granted."""
    job = session.get(Job, job_id)
    if job is None or job.kind != "mcp.execute":
        raise KeyError(job_id)
    approval = session.execute(
        select(Approval).where(Approval.resource_type == "mcp_tool", Approval.resource_id == job_id)
    ).scalars().first()
    if approval is None or approval.status != "approved":
        raise WriteNotApproved(job_id)
    if job.state == "succeeded":
        return {"status": "executed", "jobId": job_id, "result": job.result_json.get("result")}

    conn = _require(session, job.payload_json["connectionId"])
    resolved = client_for(conn, client)
    result = resolved.call_tool(job.payload_json["tool"], job.payload_json.get("arguments") or {})
    job.state = "succeeded"
    job.result_json = {"result": result}
    _audit(session, "mcp.write.executed", approval.risk, "executed",
           {"connectionId": conn.id, "tool": job.payload_json["tool"], "jobId": job_id})
    _emit(session, conn.workspace_id, "mcp.tool_executed",
          {"connectionId": conn.id, "tool": job.payload_json["tool"], "kind": "write"})
    session.flush()
    return {"status": "executed", "jobId": job_id, "result": result}


def _require(session: Session, connection_id: str) -> MCPConnection:
    conn = session.get(MCPConnection, connection_id)
    if conn is None:
        raise KeyError(connection_id)
    return conn
