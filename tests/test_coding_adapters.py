"""Adapter contract suite (batch B7).

The same assertions run against GitPilot, Claude Code, and Codex so every
executor produces an identical NormalizedRun from an identical fixture — the
guarantee DayPilot relies on to switch executors without downstream changes.
"""
from __future__ import annotations

import httpx
import pytest

from app.main import app
from daypilot_orchestrator.coding.claude_code_adapter import ClaudeCodeAdapter
from daypilot_orchestrator.coding.codex_adapter import CodexAdapter
from daypilot_orchestrator.coding.gitpilot_adapter import GitPilotAdapter
from daypilot_orchestrator.coding.interface import CodingMode, CodingRunSpec
from daypilot_orchestrator.coding.provider_routing import choose_executor
from fastapi.testclient import TestClient

client = TestClient(app)

# One recorded fixture shape all adapters must normalize identically.
FIXTURE = {
    "runId": "run-x",
    "status": "needs_review",
    "branch": "feature/y",
    "prUrl": "https://example.com/pr/1",
    "diff": {"files": [{"path": "a.py", "additions": 4, "deletions": 2}], "summary": "change a"},
    "tests": {"passed": 18, "total": 20, "failedNames": ["t1", "t2"]},
}


def _transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json=FIXTURE))


ADAPTERS = {
    "gitpilot": lambda: GitPilotAdapter(base_url="http://x", transport=_transport()),
    "claude_code": lambda: ClaudeCodeAdapter(base_url="http://x", transport=_transport()),
    "codex": lambda: CodexAdapter(base_url="http://x", transport=_transport()),
}


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_adapter_produces_identical_normalized_run(name):
    adapter = ADAPTERS[name]()
    run = adapter.create_run(CodingRunSpec(task="do", repo="o/r", mode=CodingMode.ASK))
    assert run.executor == name
    assert run.status.value == "needs_review"
    assert run.branch == "feature/y"
    assert run.pr_url == "https://example.com/pr/1"
    assert run.diff.files_changed == 1
    assert run.tests.passed == 18 and run.tests.total == 20
    assert run.tests.pass_rate == 0.9


@pytest.mark.parametrize("name", list(ADAPTERS))
def test_adapter_get_diff_and_tests_match(name):
    adapter = ADAPTERS[name]()
    assert adapter.get_diff("run-x").files_changed == 1
    assert adapter.get_tests("run-x").total == 20


def test_capabilities_differ_by_executor():
    caps = {a().capabilities.name: a().capabilities for a in ADAPTERS.values()}
    assert caps["codex"].supports_pr is False
    assert caps["claude_code"].supports_pr is True
    assert caps["gitpilot"].supports_plan_mode is True
    assert caps["codex"].supports_plan_mode is False


def test_routing_defaults_to_gitpilot_when_optional_disabled(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_ENABLED", raising=False)
    monkeypatch.delenv("CODEX_ENABLED", raising=False)
    # Requesting a disabled optional executor falls back to the default bridge.
    assert choose_executor("claude_code", None) == "gitpilot"
    assert choose_executor(None, None) == "gitpilot"


def test_routing_uses_optional_executor_when_enabled(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    assert choose_executor("claude_code", None) == "claude_code"


def test_project_override_routes_executor(monkeypatch):
    monkeypatch.setenv("CODEX_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_CODING_PROJECT_OVERRIDES", "proj-a=codex")
    assert choose_executor(None, "proj-a") == "codex"
    assert choose_executor(None, "proj-b") == "gitpilot"


def test_gateway_executors_endpoint():
    body = client.get("/v1/coding/executors").json()
    names = {e["executor"] for e in body["executors"]}
    assert {"gitpilot", "claude_code", "codex"} <= names
    gitpilot = next(e for e in body["executors"] if e["executor"] == "gitpilot")
    assert gitpilot["enabled"] is True
