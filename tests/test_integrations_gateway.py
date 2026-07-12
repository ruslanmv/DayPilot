"""Integration Gateway — Phase 1 completion criteria (batch I0/I1).

Proves the six criteria end to end through the real gateway:
  1. connect one external provider,
  2. store its credentials safely (never in DB/API responses),
  3. execute one read action,
  4. execute one write action with approval,
  5. record the action in the audit log,
  6. detect and display connection failure.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.integrations.credentials import credential_store

client = TestClient(app)


def _connect(token: str = "s3cr3t-token", provider: str = "reference") -> dict:
    r = client.post("/v1/integrations/connect", json={"provider": provider, "credentials": {"token": token}})
    assert r.status_code == 201, r.text
    return r.json()


def test_reference_provider_is_available():
    body = client.get("/v1/integrations").json()
    assert "reference" in body["available"]


def test_connect_stores_credentials_safely():
    conn = _connect(token="top-secret-value-123")
    # 2. The credential must not appear in the API response or the connection row.
    assert "top-secret-value-123" not in str(conn)
    assert "credentials" not in conn and "token" not in conn
    assert conn["status"] == "connected"
    assert "echo.read" in conn["capabilities"]
    # It IS retrievable from the out-of-DB credential store keyed by connection id.
    assert credential_store().get(conn["id"]) == {"token": "top-secret-value-123"}


def test_read_action_executes_immediately():
    conn = _connect()
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.read", "input": {"q": "hi"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "executed"
    assert body["result"] == {"echo": {"q": "hi"}}


def test_write_action_requires_approval_before_executing():
    conn = _connect()
    # 4a. A write opens an approval + a durable job; it does NOT execute yet.
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.write", "input": {"v": 1}})
    assert r.status_code == 200, r.text
    pending = r.json()
    assert pending["status"] == "approval_required"
    job_id, approval_id = pending["jobId"], pending["approvalId"]

    # 4b. Performing before approval is refused.
    early = client.post(f"/v1/integrations/actions/{job_id}/perform")
    assert early.status_code == 409

    # 4c. Approve via the Approval Center, then perform succeeds.
    dec = client.post(f"/v1/approvals/{approval_id}/decide", json={"decision": "approve"})
    assert dec.status_code == 200, dec.text
    done = client.post(f"/v1/integrations/actions/{job_id}/perform")
    assert done.status_code == 200, done.text
    assert done.json()["result"] == {"written": {"v": 1}, "ok": True}


def test_every_step_is_audited():
    conn = _connect()
    client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.read", "input": 1})
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.write", "input": 2})
    approval_id = r.json()["approvalId"]
    job_id = r.json()["jobId"]
    client.post(f"/v1/approvals/{approval_id}/decide", json={"decision": "approve"})
    client.post(f"/v1/integrations/actions/{job_id}/perform")

    export = client.get("/v1/approvals/audit/export").text
    for event_type in (
        "integration.connect",
        "integration.read.executed",
        "integration.write.requested",
        "integration.write.executed",
        "approval.decided",
    ):
        assert event_type in export
    # No credential ever appears in the audit trail.
    assert "s3cr3t-token" not in export


def test_connection_failure_is_detected_on_connect():
    # 6a. A bad credential fails the connect with a 400 and persists no connection.
    r = client.post("/v1/integrations/connect", json={"provider": "reference", "credentials": {"token": "fail"}})
    assert r.status_code == 400


def test_connection_failure_is_detected_on_refresh():
    conn = _connect()
    # Simulate a revoked/expired token, then a health refresh flips status to error.
    credential_store().put(conn["id"], {"token": "fail"})
    r = client.post(f"/v1/integrations/{conn['id']}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_unknown_capability_is_rejected():
    conn = _connect()
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.delete", "input": None})
    assert r.status_code == 404


def test_worker_auto_performs_approved_write():
    """The full loop with no manual perform: approve → a worker promotes and runs
    the gated job."""
    from daypilot_knowledge.db import Job, session_scope
    from daypilot_orchestrator.integrations.worker import run_pending

    from app.db import get_engine

    conn = _connect()
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.write", "input": {"n": 7}})
    job_id, approval_id = r.json()["jobId"], r.json()["approvalId"]
    client.post(f"/v1/approvals/{approval_id}/decide", json={"decision": "approve"})

    with session_scope(get_engine()) as s:
        processed = run_pending(s)
    assert processed >= 1

    with session_scope(get_engine()) as s:
        row = s.get(Job, job_id)
        assert row.state == "succeeded"
        assert row.result_json["result"] == {"written": {"n": 7}, "ok": True}


def test_worker_leaves_unapproved_actions_gated():
    from daypilot_knowledge.db import Job, session_scope
    from daypilot_orchestrator.integrations.worker import run_pending

    from app.db import get_engine

    conn = _connect()
    r = client.post(f"/v1/integrations/{conn['id']}/execute", json={"action": "echo.write", "input": 1})
    job_id = r.json()["jobId"]
    with session_scope(get_engine()) as s:
        run_pending(s)
        row = s.get(Job, job_id)
        assert row.state == "blocked_on_approval"  # never runs without approval


def test_disconnect_revokes_credentials():
    conn = _connect()
    assert credential_store().has(conn["id"])
    r = client.post(f"/v1/integrations/{conn['id']}/disconnect")
    assert r.status_code == 200
    assert not credential_store().has(conn["id"])
    assert client.get(f"/v1/integrations/{conn['id']}").status_code == 404
