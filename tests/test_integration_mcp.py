"""MCP tool governance — Phase 3 completion criteria (batch I4/I5).

Proves, with a fake MCP client (no live server), that an administrator can:
attach a server, inspect tools, enable selected tools, assign permissions,
let AI use an allowed read tool, require approval for a write tool, and view the
result + audit record. The AI never receives an MCP client — every call goes
through the policy + approval router.
"""
from __future__ import annotations

from typing import Any

import pytest

from daypilot_knowledge.db import create_engine_from_settings, session_scope
from daypilot_orchestrator.approvals.center import decide
from daypilot_orchestrator.integrations.mcp import service as mcp
from daypilot_orchestrator.integrations.mcp.classification import classify_tool
from daypilot_orchestrator.integrations.provider import CapabilityKind

ENGINE = create_engine_from_settings()

TOOLS = [
    {"name": "search_customers", "description": "Search CRM customers."},
    {"name": "get_customer", "description": "Fetch one customer."},
    {"name": "update_customer", "description": "Update a customer record."},
    {"name": "delete_customer", "description": "Delete a customer."},
]


class FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {"tool": name, "args": arguments, "ok": True}


def test_classification_heuristics():
    assert classify_tool("search_customers") is CapabilityKind.READ
    assert classify_tool("get_customer") is CapabilityKind.READ
    assert classify_tool("update_customer") is CapabilityKind.WRITE
    assert classify_tool("delete_customer") is CapabilityKind.DESTRUCTIVE
    # Annotation overrides the name heuristic.
    assert classify_tool("do_thing", {"readOnlyHint": True}) is CapabilityKind.READ


def _attach() -> str:
    with session_scope(ENGINE) as s:
        conn = mcp.add_server(s, "default", "Internal CRM", "streamable_http",
                              endpoint="https://mcp.company.com/mcp", client=FakeMCPClient())
    return conn["id"]


def test_attach_and_inspect_tools():
    cid = _attach()
    with session_scope(ENGINE) as s:
        tools = mcp.list_tools(s, cid)
    by_name = {t["name"]: t for t in tools}
    assert by_name["search_customers"]["kind"] == "read"
    assert by_name["search_customers"]["permission"] == "allowed"
    assert by_name["update_customer"]["kind"] == "write"
    assert by_name["update_customer"]["permission"] == "approval_required"
    assert by_name["delete_customer"]["kind"] == "destructive"
    # Tools start disabled (opt-in).
    assert all(t["enabled"] is False for t in tools)


def test_read_tool_runs_after_enable():
    cid = _attach()
    client = FakeMCPClient()
    with session_scope(ENGINE) as s:
        mcp.set_tool_enabled(s, cid, "search_customers", True)
    # Disabled tool is refused.
    with session_scope(ENGINE) as s, pytest.raises(mcp.ToolNotEnabled):
        mcp.execute_tool(s, cid, "get_customer", {}, client=client)
    # Enabled read tool runs immediately.
    with session_scope(ENGINE) as s:
        res = mcp.execute_tool(s, cid, "search_customers", {"q": "acme"}, client=client)
    assert res["status"] == "executed"
    assert res["result"]["ok"] is True


def test_write_tool_requires_approval():
    cid = _attach()
    client = FakeMCPClient()
    with session_scope(ENGINE) as s:
        mcp.set_tool_enabled(s, cid, "update_customer", True)
    with session_scope(ENGINE) as s:
        res = mcp.execute_tool(s, cid, "update_customer", {"id": 1, "name": "New"}, client=client)
    assert res["status"] == "approval_required"
    assert not client.calls  # nothing executed yet
    job_id, approval_id = res["jobId"], res["approvalId"]

    # Performing before approval is refused.
    with session_scope(ENGINE) as s, pytest.raises(mcp.WriteNotApproved):
        mcp.perform_pending_tool(s, job_id, client=client)

    # Approve, then perform.
    with session_scope(ENGINE) as s:
        decide(s, approval_id, "approve")
    with session_scope(ENGINE) as s:
        done = mcp.perform_pending_tool(s, job_id, client=client)
    assert done["result"]["ok"] is True
    assert client.calls == [("update_customer", {"id": 1, "name": "New"})]


def test_admin_override_reclassifies_tool():
    cid = _attach()
    client = FakeMCPClient()
    with session_scope(ENGINE) as s:
        mcp.set_tool_enabled(s, cid, "search_customers", True)
        mcp.override_classification(s, cid, "search_customers", "write")  # admin says it's a write
    # Now the "read-looking" tool requires approval.
    with session_scope(ENGINE) as s:
        res = mcp.execute_tool(s, cid, "search_customers", {}, client=client)
    assert res["status"] == "approval_required"


def test_audit_records_every_step():
    from app.main import app
    from fastapi.testclient import TestClient
    api = TestClient(app)

    cid = _attach()
    with session_scope(ENGINE) as s:
        mcp.set_tool_enabled(s, cid, "update_customer", True)
    with session_scope(ENGINE) as s:
        res = mcp.execute_tool(s, cid, "update_customer", {"id": 2}, client=FakeMCPClient())
        approval_id, job_id = res["approvalId"], res["jobId"]
    with session_scope(ENGINE) as s:
        decide(s, approval_id, "approve")
    with session_scope(ENGINE) as s:
        mcp.perform_pending_tool(s, job_id, client=FakeMCPClient())

    export = api.get("/v1/approvals/audit/export").text
    for event_type in ("mcp.attached", "mcp.write.requested", "mcp.write.executed"):
        assert event_type in export
