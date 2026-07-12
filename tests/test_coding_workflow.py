"""Tests for the coding workflow: GitPilot adapter, risk, and governance (B6)."""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.coding.gitpilot_adapter import GitPilotAdapter
from daypilot_orchestrator.coding.interface import (
    CodingMode,
    CodingRunSpec,
    DiffSummary,
    FileChange,
    TestResults,
)
from daypilot_orchestrator.coding.risk import score_risk

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- Risk scoring -----------------------------------------------------------

def test_risk_low_for_small_green_change():
    diff = DiffSummary(files=[FileChange("app/util.py", 5, 1)])
    level, score, _ = score_risk(diff, TestResults(passed=10, total=10))
    assert level == "low"
    assert score < 30


def test_risk_high_for_large_failing_sensitive_change():
    files = [FileChange(f"src/f{i}.py", 30, 10) for i in range(25)]
    files.append(FileChange("alembic/versions/0003.py", 40, 0))
    diff = DiffSummary(files=files)
    level, score, reasons = score_risk(diff, TestResults(passed=100, total=200))
    assert level == "high"
    assert any("sensitive" in r for r in reasons)


# --- GitPilot adapter normalization (modern + legacy shapes) ----------------

def _transport(payload: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-DayPilot-Adapter-Version")
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_adapter_normalizes_modern_shape():
    payload = {
        "runId": "gp-1",
        "status": "needs_review",
        "branch": "feature/x",
        "prUrl": "https://github.com/o/r/pull/1",
        "diff": {"files": [{"path": "a.py", "additions": 3, "deletions": 1}], "summary": "add a"},
        "tests": {"passed": 9, "total": 10, "failedNames": ["t_edge"]},
    }
    adapter = GitPilotAdapter(base_url="http://gp.test", transport=_transport(payload))
    run = adapter.create_run(CodingRunSpec(task="do", repo="o/r", mode=CodingMode.ASK))
    assert run.executor == "gitpilot"
    assert run.status.value == "needs_review"
    assert run.diff.files_changed == 1
    assert run.tests.pass_rate == 0.9


def test_adapter_tolerates_legacy_shape():
    # Older GitPilot: id/state/changed_files/test_summary.
    payload = {
        "id": "legacy-7",
        "state": "review",
        "changed_files": ["x.py", "y.py"],
        "test_summary": "18/20",
    }
    adapter = GitPilotAdapter(base_url="http://gp.test", transport=_transport(payload))
    run = adapter.create_run(CodingRunSpec(task="do", repo="o/r"))
    assert run.run_id == "legacy-7"
    assert run.status.value == "needs_review"
    assert run.diff.files_changed == 2
    assert run.tests.passed == 18 and run.tests.total == 20


# --- Governance via the gateway (patched adapter) ---------------------------

@pytest.fixture()
def patched_gitpilot(monkeypatch):
    payload = {
        "runId": "gp-42",
        "status": "needs_review",
        "branch": "feature/api",
        "diff": {"files": [{"path": "svc.py", "additions": 12, "deletions": 4}], "summary": "impl"},
        "tests": {"passed": 20, "total": 20},
    }
    from daypilot_orchestrator.coding import provider_routing

    def fake_resolve(executor=None, *, project_id=None, transport=None):
        return GitPilotAdapter(base_url="http://gp.test", transport=_transport(payload))

    monkeypatch.setattr(provider_routing, "resolve_adapter", fake_resolve)
    # The router imports the symbol directly, so patch it there too.
    from app.routers import coding as coding_router

    monkeypatch.setattr(coding_router, "resolve_adapter", fake_resolve)
    return payload


def test_create_run_opens_approval_and_review_window(patched_gitpilot):
    ws = _ws()
    created = client.post(
        "/v1/coding/runs",
        json={"task": "Implement API", "repo": "ruslanmv/DayPilot", "workspaceId": ws},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["executor"] == "gitpilot"
    assert body["status"] == "needs_review"
    assert body["approvalStatus"] == "pending"

    # A review-window task is scheduled in the plan ledger.
    review_tasks = [t for t in client.get(f"/v1/tasks?workspaceId={ws}&limit=50").json()["items"]
                    if t["title"].startswith("Review patch")]
    assert review_tasks


def test_write_blocked_until_approved(patched_gitpilot):
    ws = _ws()
    run = client.post(
        "/v1/coding/runs",
        json={"task": "t", "repo": "o/r", "workspaceId": ws},
    ).json()
    run_id = run["id"]

    # Write before approval is refused server-side.
    blocked = client.post(f"/v1/coding/runs/{run_id}/write")
    assert blocked.status_code == 403

    # Approve, then write succeeds and marks merged.
    approved = client.post(f"/v1/coding/runs/{run_id}/review", json={"decision": "approve"})
    assert approved.json()["status"] == "approved"
    written = client.post(f"/v1/coding/runs/{run_id}/write")
    assert written.status_code == 200
    assert written.json()["status"] == "merged"


def test_reject_sets_status(patched_gitpilot):
    ws = _ws()
    run = client.post("/v1/coding/runs", json={"task": "t", "repo": "o/r", "workspaceId": ws}).json()
    rejected = client.post(f"/v1/coding/runs/{run['id']}/review", json={"decision": "reject", "reason": "scope"})
    assert rejected.json()["status"] == "rejected"
    # Write still refused after rejection.
    assert client.post(f"/v1/coding/runs/{run['id']}/write").status_code == 403
