"""Coding workflow interface (batch B6).

One normalized contract that GitPilot (default), Claude Code, and Codex all
implement, so DayPilot can see and steer coding work across many repositories
the same way regardless of which executor runs it: branch, PR, tests, diff,
risk, and next action.

The adapter never performs a repository write on its own — DayPilot's approval
layer gates writes. Adapters propose; the platform decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class CodingMode(StrEnum):
    """Execution mode, mapped onto DayPilot approval policy.

    ASK  -> approval-gated (default): human approves each dangerous action.
    AUTO -> only permitted for personas in ENABLED_AUTONOMOUS_LIMITED.
    PLAN -> read-only: produce a plan/diff, never write.
    """

    ASK = "ask"
    AUTO = "auto"
    PLAN = "plan"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    FAILED = "failed"


@dataclass(frozen=True)
class CodingRunSpec:
    """What DayPilot asks an executor to do."""

    task: str
    repo: str
    mode: CodingMode = CodingMode.ASK
    branch: str | None = None
    base_branch: str = "main"
    workspace_id: str = "default"
    project_id: str | None = None
    task_id: str | None = None


@dataclass
class FileChange:
    path: str
    additions: int = 0
    deletions: int = 0


@dataclass
class DiffSummary:
    files: list[FileChange] = field(default_factory=list)
    patch: str = ""
    human_summary: str = ""

    @property
    def files_changed(self) -> int:
        return len(self.files)

    @property
    def total_lines(self) -> int:
        return sum(f.additions + f.deletions for f in self.files)


@dataclass
class TestResults:
    __test__ = False  # not a pytest test class despite the Test* name

    passed: int | None = None
    total: int | None = None
    failed_names: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float | None:
        if not self.total:
            return None
        passed = self.passed or 0
        return round(passed / self.total, 3)


@dataclass
class NormalizedRun:
    """Executor-agnostic view of a coding run."""

    run_id: str
    executor: str
    status: RunStatus
    repo: str
    mode: CodingMode
    branch: str | None = None
    pr_url: str | None = None
    diff: DiffSummary = field(default_factory=DiffSummary)
    tests: TestResults = field(default_factory=TestResults)
    detail: str = ""


@dataclass(frozen=True)
class AdapterCapabilities:
    """What an executor can do, so routing and the UI can adapt."""

    name: str
    supports_tests: bool
    supports_pr: bool
    supports_plan_mode: bool
    diff_granularity: str  # "file" | "hunk" | "line"
    session_continuity: bool = False


class CodingWorkflowAdapter(Protocol):
    """Every coding executor implements this identical surface."""

    capabilities: AdapterCapabilities

    def create_run(self, spec: CodingRunSpec) -> NormalizedRun: ...

    def get_run(self, run_id: str) -> NormalizedRun: ...

    def get_diff(self, run_id: str) -> DiffSummary: ...

    def get_tests(self, run_id: str) -> TestResults: ...

    def cancel(self, run_id: str) -> NormalizedRun: ...
