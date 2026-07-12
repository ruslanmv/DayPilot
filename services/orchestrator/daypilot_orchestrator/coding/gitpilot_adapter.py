"""GitPilot adapter — DayPilot's default, retro-compatible coding bridge (B6).

Drives GitPilot's A2A-secured runner (`POST /api/v1/gitpilot/runs`) and
normalizes its response into the shared coding contract. GitPilot's Ask/Auto/
Plan modes map onto DayPilot approval policy, and the adapter negotiates its
version so it tolerates older GitPilot response shapes (the "retro-compatible"
guarantee).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from .interface import (
    AdapterCapabilities,
    CodingMode,
    CodingRunSpec,
    DiffSummary,
    NormalizedRun,
    TestResults,
)
from .normalize import normalize_run

ADAPTER_VERSION = "1.0.0"
DEFAULT_TIMEOUT = 120.0


@dataclass
class GitPilotAdapter:
    base_url: str
    api_key: str | None = None
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    timeout: float = DEFAULT_TIMEOUT
    capabilities: AdapterCapabilities = field(
        default_factory=lambda: AdapterCapabilities(
            name="gitpilot",
            supports_tests=True,
            supports_pr=True,
            supports_plan_mode=True,
            diff_granularity="hunk",
            session_continuity=True,
        )
    )

    def _client(self) -> httpx.Client:
        headers = {
            # Version negotiation: GitPilot can tailor its response shape, and
            # we tolerate older shapes when it does not.
            "X-DayPilot-Adapter-Version": ADAPTER_VERSION,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.base_url.rstrip("/"), headers=headers, timeout=self.timeout,
            transport=self.transport,
        )

    # --- CodingWorkflowAdapter surface -------------------------------------

    def create_run(self, spec: CodingRunSpec) -> NormalizedRun:
        payload = {
            "task": spec.task,
            "repo": spec.repo,
            "mode": spec.mode.value,
            "branch": spec.branch,
            "baseBranch": spec.base_branch,
        }
        with self._client() as client:
            response = client.post("/api/v1/gitpilot/runs", json=payload)
            response.raise_for_status()
            data = response.json()
        return self._normalize(data, spec.repo, spec.mode)

    def get_run(self, run_id: str) -> NormalizedRun:
        with self._client() as client:
            response = client.get(f"/api/v1/gitpilot/runs/{run_id}")
            response.raise_for_status()
            data = response.json()
        return self._normalize(data)

    def get_diff(self, run_id: str) -> DiffSummary:
        return self.get_run(run_id).diff

    def get_tests(self, run_id: str) -> TestResults:
        return self.get_run(run_id).tests

    def cancel(self, run_id: str) -> NormalizedRun:
        with self._client() as client:
            response = client.post(f"/api/v1/gitpilot/runs/{run_id}/cancel")
            response.raise_for_status()
            data = response.json()
        return self._normalize(data)

    # --- Normalization (retro-compatible, shared) --------------------------

    @staticmethod
    def _normalize(data: dict, repo: str | None = None, mode: CodingMode | None = None) -> NormalizedRun:
        return normalize_run(data, "gitpilot", repo, mode)


def gitpilot_from_env(transport: httpx.BaseTransport | None = None) -> GitPilotAdapter:
    return GitPilotAdapter(
        base_url=os.getenv("GITPILOT_URL", "http://localhost:8200"),
        api_key=os.getenv("GITPILOT_API_KEY") or None,
        transport=transport,
    )
