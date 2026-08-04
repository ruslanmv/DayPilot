"""Shared response normalization for coding adapters (batch B6/B7).

Keeps the retro-compatible parsing (modern + legacy shapes) in one place so
GitPilot, Claude Code, and Codex adapters all produce identical NormalizedRun
objects regardless of the executor's native response format.
"""
from __future__ import annotations

from .interface import (
    CodingMode,
    DiffSummary,
    FileChange,
    NormalizedRun,
    RunStatus,
    TestResults,
)

STATUS_ALIASES = {
    "queued": RunStatus.QUEUED,
    "pending": RunStatus.QUEUED,
    "running": RunStatus.RUNNING,
    "in_progress": RunStatus.RUNNING,
    "needs_review": RunStatus.NEEDS_REVIEW,
    "review": RunStatus.NEEDS_REVIEW,
    "awaiting_review": RunStatus.NEEDS_REVIEW,
    # An executor reporting "completed"/"needs_approval" means it finished
    # PRODUCING work — never that the work was written. It maps to NEEDS_REVIEW
    # so the approval gate still stands; mapping it to MERGED would claim a
    # repository write that never happened.
    "completed": RunStatus.NEEDS_REVIEW,
    "complete": RunStatus.NEEDS_REVIEW,
    "succeeded": RunStatus.NEEDS_REVIEW,
    "needs_approval": RunStatus.NEEDS_REVIEW,
    # Refused by the executor's own guardrails (e.g. a forbidden path).
    "blocked": RunStatus.FAILED,
    "cancelled": RunStatus.FAILED,
    "canceled": RunStatus.FAILED,
    "approved": RunStatus.APPROVED,
    "rejected": RunStatus.REJECTED,
    "merged": RunStatus.MERGED,
    "done": RunStatus.MERGED,
    "failed": RunStatus.FAILED,
    "error": RunStatus.FAILED,
}


def normalize_diff(data: dict) -> DiffSummary:
    diff_raw = data.get("diff") or {}
    files_raw = diff_raw.get("files") or data.get("changed_files") or data.get("files") or []
    files: list[FileChange] = []
    for entry in files_raw:
        if isinstance(entry, str):
            files.append(FileChange(path=entry))
        elif isinstance(entry, dict):
            files.append(
                FileChange(
                    path=entry.get("path") or entry.get("file") or "",
                    additions=int(entry.get("additions") or entry.get("added") or 0),
                    deletions=int(entry.get("deletions") or entry.get("removed") or 0),
                )
            )
    return DiffSummary(
        files=files,
        patch=diff_raw.get("patch") or data.get("patch") or "",
        human_summary=diff_raw.get("humanSummary")
        or diff_raw.get("summary")
        or data.get("summary")
        or "",
    )


def normalize_tests(data: dict) -> TestResults:
    tests_raw = data.get("tests") or {}
    passed = tests_raw.get("passed")
    total = tests_raw.get("total")
    failed = tests_raw.get("failedNames") or tests_raw.get("failed") or []
    if (passed is None or total is None) and isinstance(data.get("test_summary"), str):
        summary = data["test_summary"]
        if "/" in summary:
            try:
                p, t = summary.split("/", 1)
                passed, total = int(p), int(t)
            except ValueError:
                pass
    # Executors that report a verdict instead of counts (GitPilot's
    # `test_status`) keep it categorical — never invented as a pass total.
    status = str(tests_raw.get("status") or data.get("test_status") or "")
    return TestResults(
        passed=passed,
        total=total,
        failed_names=[str(f) for f in failed] if isinstance(failed, list) else [],
        status=status,
    )


def normalize_run(
    data: dict, executor: str, repo: str | None = None, mode: CodingMode | None = None
) -> NormalizedRun:
    run_id = data.get("runId") or data.get("id") or data.get("run_id") or ""
    raw_status = (data.get("status") or data.get("state") or "queued").lower()
    status = STATUS_ALIASES.get(raw_status, RunStatus.QUEUED)
    repo_value = data.get("repo") or repo or ""
    mode_value = CodingMode(data["mode"]) if data.get("mode") else (mode or CodingMode.ASK)
    return NormalizedRun(
        run_id=run_id,
        executor=executor,
        status=status,
        repo=repo_value,
        mode=mode_value,
        branch=data.get("branch"),
        pr_url=data.get("prUrl") or data.get("pr_url") or data.get("pullRequestUrl"),
        diff=normalize_diff(data),
        tests=normalize_tests(data),
        detail=data.get("detail") or data.get("message") or "",
    )
