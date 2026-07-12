"""Coding run orchestration and governance (batch B6).

Persists normalized coding runs, scores their risk, opens an approval for any
repository write, schedules a review window in the day plan, and audits every
run, decision, and write. The write itself is refused unless an approval record
is approved — enforced here on the server, not in the UI.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, CodingRun, Event, Task

from .interface import CodingRunSpec, CodingWorkflowAdapter, NormalizedRun, RunStatus
from .risk import score_risk

EVENT_APPROVAL_REQUESTED = "approval.requested"
EVENT_AGENT_STATE = "agent.state_changed"

WRITE_ACTION = "git.write"


class WriteNotApproved(PermissionError):
    """Raised when a repository write is attempted without an approved approval."""


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _audit(session: Session, event_type: str, risk: str, decision: str, payload: dict[str, Any]) -> None:
    session.add(AuditLog(event_type=event_type, risk=risk, decision=decision, payload_json=payload))


def _serialize(run: CodingRun, approval: Approval | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "workspaceId": run.workspace_id,
        "executor": run.executor,
        "repo": run.repo,
        "branch": run.branch,
        "prUrl": run.pr_url,
        "mode": run.mode,
        "status": run.status,
        "filesChanged": run.files_changed,
        "testsPassed": run.tests_passed,
        "testsTotal": run.tests_total,
        "risk": run.risk,
        "riskScore": run.risk_score,
        "diffSummary": run.diff_summary,
        "taskId": run.task_id,
        "projectId": run.project_id,
        "approvalId": approval.id if approval else None,
        "approvalStatus": approval.status if approval else None,
    }


def create_coding_run(
    session: Session, adapter: CodingWorkflowAdapter, spec: CodingRunSpec
) -> dict[str, Any]:
    """Run an executor, persist the normalized result, and open governance."""
    normalized: NormalizedRun = adapter.create_run(spec)
    level, score, reasons = score_risk(normalized.diff, normalized.tests)

    run = CodingRun(
        workspace_id=spec.workspace_id,
        task_id=spec.task_id,
        project_id=spec.project_id,
        executor=normalized.executor,
        repo=normalized.repo,
        branch=normalized.branch,
        pr_url=normalized.pr_url,
        mode=normalized.mode.value,
        status=normalized.status.value,
        files_changed=normalized.diff.files_changed,
        tests_passed=normalized.tests.passed,
        tests_total=normalized.tests.total,
        risk=level,
        risk_score=score,
        diff_summary=normalized.diff.human_summary or "; ".join(reasons),
    )
    session.add(run)
    session.flush()

    # Open a pending approval for the eventual write, and schedule a review window.
    approval = Approval(
        workspace_id=spec.workspace_id,
        action=WRITE_ACTION,
        summary=f"Review {normalized.executor} patch for {normalized.repo} "
        f"({run.files_changed} files, risk {level}).",
        risk=level,
        status="pending",
        resource_type="coding_run",
        resource_id=run.id,
    )
    session.add(approval)
    _schedule_review_window(session, spec.workspace_id, run)

    _emit(
        session, spec.workspace_id, EVENT_APPROVAL_REQUESTED,
        {"resourceType": "coding_run", "resourceId": run.id, "risk": level, "riskScore": score},
    )
    _audit(session, "coding.run_created", level, "recorded",
           {"runId": run.id, "executor": run.executor, "repo": run.repo, "riskReasons": reasons})
    session.flush()
    return _serialize(run, approval)


def _schedule_review_window(session: Session, workspace_id: str, run: CodingRun) -> None:
    session.add(
        Task(
            workspace_id=workspace_id,
            title=f"Review patch: {run.repo}",
            owner="you",
            executor=run.executor,
            priority="high" if run.risk == "high" else "medium",
            status="scheduled",
            source="coding_review",
            risk=run.risk,
            project_id=run.project_id,
            context=f"Approve the {run.executor} patch before it writes to {run.repo}.",
            next_action="Open patch review and approve, request changes, or reject.",
        )
    )


def get_coding_run(session: Session, run_id: str) -> dict[str, Any] | None:
    run = session.get(CodingRun, run_id)
    if run is None:
        return None
    approval = _approval_for(session, run.id)
    return _serialize(run, approval)


def _approval_for(session: Session, run_id: str) -> Approval | None:
    return session.execute(
        select(Approval).where(
            Approval.resource_type == "coding_run", Approval.resource_id == run_id
        ).order_by(Approval.created_at.desc())
    ).scalars().first()


def review_coding_run(
    session: Session, run_id: str, decision: str, reason: str | None = None
) -> dict[str, Any]:
    """Apply a review decision: approve | request_changes | reject."""
    run = session.get(CodingRun, run_id)
    if run is None:
        raise KeyError(run_id)
    approval = _approval_for(session, run.id)
    if decision == "approve":
        run.status = RunStatus.APPROVED.value
        if approval:
            approval.status = "approved"
    elif decision == "reject":
        run.status = RunStatus.REJECTED.value
        if approval:
            approval.status = "rejected"
    elif decision == "request_changes":
        run.status = RunStatus.NEEDS_REVIEW.value
    else:
        raise ValueError(f"Unknown review decision: {decision}")
    if approval:
        approval.reason = reason
        approval.decided_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    _emit(session, run.workspace_id, EVENT_AGENT_STATE,
          {"resourceType": "coding_run", "resourceId": run.id, "status": run.status})
    _audit(session, "coding.reviewed", run.risk, decision, {"runId": run.id, "reason": reason})
    session.flush()
    return _serialize(run, approval)


def perform_write(session: Session, run_id: str) -> dict[str, Any]:
    """Merge / create PR. Refused unless the run's approval is approved."""
    run = session.get(CodingRun, run_id)
    if run is None:
        raise KeyError(run_id)
    approval = _approval_for(session, run.id)
    if approval is None or approval.status != "approved":
        _audit(session, "coding.write_blocked", run.risk, "blocked",
               {"runId": run.id, "reason": "no approved approval"})
        raise WriteNotApproved(
            f"Write to {run.repo} refused: coding run {run.id} has no approved approval."
        )
    run.status = RunStatus.MERGED.value
    run.updated_at = datetime.utcnow()
    _emit(session, run.workspace_id, EVENT_AGENT_STATE,
          {"resourceType": "coding_run", "resourceId": run.id, "status": run.status})
    _audit(session, "coding.write_performed", run.risk, "approved", {"runId": run.id, "repo": run.repo})
    session.flush()
    return _serialize(run, approval)
