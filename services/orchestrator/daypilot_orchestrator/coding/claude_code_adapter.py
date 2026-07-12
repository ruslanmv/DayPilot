"""Claude Code executor adapter (batch B7).

An optional coding executor behind the same CodingWorkflowAdapter interface as
GitPilot. A deployment points CLAUDE_CODE_URL at whatever bridge exposes Claude
Code runs; DayPilot governs the result identically (approval-gated writes).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from .interface import (
    AdapterCapabilities,
    CodingRunSpec,
    DiffSummary,
    NormalizedRun,
    TestResults,
)
from .normalize import normalize_run

DEFAULT_TIMEOUT = 180.0


@dataclass
class ClaudeCodeAdapter:
    base_url: str
    api_key: str | None = None
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout: float = DEFAULT_TIMEOUT
    capabilities: AdapterCapabilities = field(
        default_factory=lambda: AdapterCapabilities(
            name="claude_code",
            supports_tests=True,
            supports_pr=True,
            supports_plan_mode=True,
            diff_granularity="line",
            session_continuity=True,
        )
    )

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.base_url.rstrip("/"), headers=headers, timeout=self.timeout,
            transport=self.transport,
        )

    def create_run(self, spec: CodingRunSpec) -> NormalizedRun:
        payload = {"task": spec.task, "repo": spec.repo, "mode": spec.mode.value, "branch": spec.branch}
        with self._client() as client:
            response = client.post("/v1/claude-code/runs", json=payload)
            response.raise_for_status()
            data = response.json()
        return normalize_run(data, "claude_code", spec.repo, spec.mode)

    def get_run(self, run_id: str) -> NormalizedRun:
        with self._client() as client:
            response = client.get(f"/v1/claude-code/runs/{run_id}")
            response.raise_for_status()
            data = response.json()
        return normalize_run(data, "claude_code")

    def get_diff(self, run_id: str) -> DiffSummary:
        return self.get_run(run_id).diff

    def get_tests(self, run_id: str) -> TestResults:
        return self.get_run(run_id).tests

    def cancel(self, run_id: str) -> NormalizedRun:
        with self._client() as client:
            response = client.post(f"/v1/claude-code/runs/{run_id}/cancel")
            response.raise_for_status()
            data = response.json()
        return normalize_run(data, "claude_code")


def claude_code_from_env(transport: httpx.BaseTransport | None = None) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        base_url=os.getenv("CLAUDE_CODE_URL", "http://localhost:8210"),
        api_key=os.getenv("CLAUDE_CODE_API_KEY") or None,
        transport=transport,
    )
