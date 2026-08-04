"""Consumer-driven contract: DayPilot → GitPilot coding runs.

DayPilot is the *consumer* of GitPilot's ``/api/v1/gitpilot/runs`` facade. This
file pins the exact request DayPilot emits and the exact response shape it must
be able to normalize. GitPilot's repo carries the mirror of this contract
(``tests/test_daypilot_contract.py``) and replays the same payload against its
real router, so a drift on either side fails a test instead of failing silently
in production.

Keep DAYPILOT_RUN_REQUEST and GITPILOT_RUN_STATUS identical in both repos.
"""
from __future__ import annotations

import httpx

from daypilot_orchestrator.coding.gitpilot_adapter import GitPilotAdapter
from daypilot_orchestrator.coding.interface import CodingMode, CodingRunSpec, RunStatus

# ── The contract ────────────────────────────────────────────────────────────
# What DayPilot sends to POST /api/v1/gitpilot/runs.
DAYPILOT_RUN_REQUEST = {
    "task": "Add a health endpoint",
    "repo": "https://github.com/acme/widget",
    "mode": "ask",
    "branch": "feature/health",
    "baseBranch": "main",
}

# What GitPilot returns from GET /api/v1/gitpilot/runs/{id} once terminal.
GITPILOT_RUN_STATUS = {
    "run_id": "gp-run-abc123",
    "status": "completed",
    "summary": "Added /health returning ok.",
    "diff_url": "http://gitpilot.local/api/v1/gitpilot/runs/gp-run-abc123/diff",
    "logs_url": "http://gitpilot.local/api/v1/gitpilot/runs/gp-run-abc123/logs",
    "test_status": "passed",
    "changed_files": ["app/main.py", "tests/test_health.py"],
    "repo": "https://github.com/acme/widget",
    "branch": "feature/health",
}


def _adapter(handler) -> GitPilotAdapter:
    return GitPilotAdapter(base_url="http://gitpilot.local", api_key="a2a-secret",
                           transport=httpx.MockTransport(handler))


def test_create_run_emits_the_pinned_request_contract():
    """The payload GitPilot's facade must accept — pinned field-for-field."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"run_id": "gp-run-abc123", "status": "queued"})

    run = _adapter(handler).create_run(CodingRunSpec(
        task="Add a health endpoint",
        repo="https://github.com/acme/widget",
        mode=CodingMode.ASK,
        branch="feature/health",
        base_branch="main",
    ))

    assert seen["path"] == "/api/v1/gitpilot/runs"
    assert seen["auth"] == "Bearer a2a-secret"  # A2A shared secret
    assert seen["body"] == DAYPILOT_RUN_REQUEST  # exact contract, no drift
    assert run.run_id == "gp-run-abc123" and run.status is RunStatus.QUEUED


def test_normalizes_gitpilot_terminal_status():
    """GitPilot's real response must normalize without losing information."""
    run = _adapter(lambda r: httpx.Response(200, json=GITPILOT_RUN_STATUS)).get_run("gp-run-abc123")

    # "completed" means the executor finished producing work — NOT that a write
    # happened. It must land in review, keeping the approval gate intact.
    assert run.status is RunStatus.NEEDS_REVIEW
    assert run.status is not RunStatus.MERGED
    assert run.executor == "gitpilot"
    assert [f.path for f in run.diff.files] == ["app/main.py", "tests/test_health.py"]
    assert run.diff.human_summary == "Added /health returning ok."
    assert run.repo == "https://github.com/acme/widget"
    assert run.branch == "feature/health"
    # A categorical verdict is preserved, never faked into counts.
    assert run.tests.status == "passed"
    assert run.tests.passed is None and run.tests.total is None


def test_executor_guardrail_states_are_not_success():
    """A refused or cancelled run must never read as reviewable work."""
    for raw in ("blocked", "error", "cancelled"):
        run = _adapter(
            lambda r, s=raw: httpx.Response(200, json={"run_id": "x", "status": s})
        ).get_run("x")
        assert run.status is RunStatus.FAILED, raw
