"""The repository a project builds in, and which AI coder writes the patch.

Two independent choices, both made once and then inherited: the repo belongs to
the project, and the coder is picked per run inside whichever executor governs
it. Neither is invented — a run with no repository is refused, and the coder
picker is populated from what the executor reports it can actually run.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.coding.gitpilot_adapter import GitPilotAdapter
from daypilot_orchestrator.coding.interface import CoderSpec, CodingMode, CodingRunSpec

client = TestClient(app)

GITPILOT_RUN = {
    "runId": "gp-run-1", "status": "completed", "branch": "gitpilot/t-1",
    "filesChanged": [{"path": "src/app.py", "additions": 4, "deletions": 0}],
    "tests": {"passed": 3, "total": 3, "status": "passed"},
}

CODERS = {
    "coders": [
        {"id": "ollabridge", "label": "Built-in coder", "kind": "model",
         "available": True, "reason": "", "default": True},
        {"id": "claude_code", "label": "Claude Code", "kind": "agent",
         "available": False, "reason": "'claude' is not installed on the GitPilot host",
         "default": False},
        {"id": "codex", "label": "Codex", "kind": "agent",
         "available": True, "reason": "", "default": False},
    ],
    "default": "ollabridge",
}


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


def _adapter(capture: dict | None = None, coders: dict | None = None) -> GitPilotAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/coders"):
            if coders is None:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json=coders)
        if capture is not None:
            capture["payload"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=GITPILOT_RUN)

    return GitPilotAdapter(base_url="http://gp.test", transport=httpx.MockTransport(handler))


# --- The coder reaches GitPilot ---------------------------------------------

def test_the_chosen_coder_is_sent_with_the_run():
    capture: dict = {}
    _adapter(capture).create_run(
        CodingRunSpec(task="add a health endpoint", repo="https://git.example/acme/app",
                      mode=CodingMode.ASK, coder=CoderSpec(provider="claude_code", model="sonnet"))
    )
    assert capture["payload"]["coder"] == {"provider": "claude_code", "model": "sonnet"}


def test_no_coder_means_the_deployment_default_and_an_unchanged_payload():
    """A GitPilot that predates coder selection must see exactly what it saw before."""
    capture: dict = {}
    _adapter(capture).create_run(
        CodingRunSpec(task="t", repo="https://git.example/acme/app")
    )
    assert "coder" not in capture["payload"]


# --- The picker is populated from the truth ---------------------------------

def test_available_coders_come_from_the_executor():
    coders = _adapter(coders=CODERS).available_coders()
    assert [c["id"] for c in coders] == ["ollabridge", "claude_code", "codex"]
    unavailable = next(c for c in coders if not c["available"])
    assert unavailable["reason"], "an unavailable coder must say why"


def test_an_executor_that_cannot_answer_offers_nothing_rather_than_guessing():
    assert _adapter(coders=None).available_coders() == []


def test_coders_endpoint_reports_unreachable_instead_of_an_empty_list(monkeypatch):
    from app.routers import coding as coding_router

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        coding_router, "resolve_adapter",
        lambda *a, **k: GitPilotAdapter(
            base_url="http://gp.test", transport=httpx.MockTransport(unreachable)
        ),
    )
    body = client.get("/v1/coding/coders").json()
    assert body["coders"] == [] and body["reachable"] is False


def test_coders_endpoint_serves_what_the_executor_reports(monkeypatch):
    from app.routers import coding as coding_router

    monkeypatch.setattr(coding_router, "resolve_adapter", lambda *a, **k: _adapter(coders=CODERS))
    body = client.get("/v1/coding/coders").json()
    assert body["reachable"] is True
    assert {c["id"] for c in body["coders"]} == {"ollabridge", "claude_code", "codex"}


# --- The repository belongs to the project ----------------------------------

@pytest.fixture()
def patched_executor(monkeypatch):
    capture: dict = {}
    from app.routers import coding as coding_router

    monkeypatch.setattr(coding_router, "resolve_adapter", lambda *a, **k: _adapter(capture))
    return capture


def _project(ws: str, repository: str = "") -> str:
    resp = client.post(
        "/v1/projects",
        json={"name": "Widget", "workspaceId": ws, "repository": repository},
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_a_project_remembers_its_repository():
    ws = _ws()
    project_id = _project(ws, "https://git.example/acme/widget")
    project = client.get(f"/v1/projects/{project_id}").json()
    assert project["repository"] == "https://git.example/acme/widget"


def test_a_run_on_a_project_inherits_its_repository(patched_executor):
    ws = _ws()
    project_id = _project(ws, "https://git.example/acme/widget")
    resp = client.post(
        "/v1/coding/runs",
        json={"task": "add a health endpoint", "workspaceId": ws, "projectId": project_id},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["repo"] == "https://git.example/acme/widget"
    assert patched_executor["payload"]["repo"] == "https://git.example/acme/widget"


def test_an_explicit_repo_still_wins(patched_executor):
    ws = _ws()
    project_id = _project(ws, "https://git.example/acme/widget")
    resp = client.post(
        "/v1/coding/runs",
        json={"task": "t", "repo": "https://git.example/acme/other",
              "workspaceId": ws, "projectId": project_id},
    )
    assert resp.json()["repo"] == "https://git.example/acme/other"


def test_a_run_with_no_repository_anywhere_is_refused(patched_executor):
    """Better a clear 400 than a run that quietly builds nothing."""
    ws = _ws()
    project_id = _project(ws)
    resp = client.post(
        "/v1/coding/runs", json={"task": "t", "workspaceId": ws, "projectId": project_id}
    )
    assert resp.status_code == 400
    assert "repository" in resp.json()["detail"]


def test_the_coder_choice_travels_from_the_api_to_the_executor(patched_executor):
    ws = _ws()
    resp = client.post(
        "/v1/coding/runs",
        json={"task": "t", "repo": "https://git.example/acme/app", "workspaceId": ws,
              "coder": {"provider": "codex", "model": ""}},
    )
    assert resp.status_code == 201
    assert patched_executor["payload"]["coder"]["provider"] == "codex"
