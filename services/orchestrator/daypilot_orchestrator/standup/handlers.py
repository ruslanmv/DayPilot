"""What actually runs the standup when nobody is watching.

The rest of this package is driven by API calls. This module is what makes the
feature *a daily habit rather than a button*: the two durable job kinds the
scheduler enqueues, and the handler map a worker needs to execute them.

    standup.review_due   17:45–18:00 → collect evidence, build the draft,
                                       notify, and schedule the next occurrence
    standup.deliver      next morning → resolve the thread, post the approved
                                       snapshot, exactly once

Two properties are load-bearing:

* **The chain never breaks.** ``review_due`` schedules the following day's
  occurrence *before* it can fail on anything else. A workflow that errors once
  must not silently stop running forever — that is the failure mode where a
  user discovers in a week that their standup has been quietly dead.
* **Retries are safe.** Both handlers are idempotent: collection dedupes,
  generation refuses to overwrite a sent day, and delivery reports the original
  message rather than posting twice.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from daypilot_knowledge.db import StandupDraft, StandupWorkflow

from ..integrations.notifications import normalize, record_notification
from . import policy, schedule, service
from .delivery import slack_history_reader, slack_sender

#: Job kinds this module handles.
REVIEW_DUE = "standup.review_due"
DELIVER = "standup.deliver"


def _workflow(session: Session, payload: dict[str, Any]) -> StandupWorkflow:
    workflow = session.get(StandupWorkflow, str(payload.get("workflowId") or ""))
    if workflow is None:
        raise LookupError(f"standup workflow {payload.get('workflowId')!r} not found")
    return workflow


def _reporting_day(workflow: StandupWorkflow, payload: dict[str, Any]) -> date:
    """The day being reported on.

    Taken from the job so a late-running worker still reports the day the job
    was scheduled for, not the day it happened to wake up on.
    """
    raw = str(payload.get("reportingDate") or "")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return schedule.local_now(schedule.zone(workflow.timezone)).date()


def handle_review_due(
    session: Session,
    payload: dict[str, Any],
    *,
    github_reader: Any = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Collect the day, build the draft, and arm tomorrow."""
    workflow = _workflow(session, payload)
    reporting_day = _reporting_day(workflow, payload)

    # Arm the next occurrence first. Everything after this can fail without
    # taking the workflow off the schedule permanently.
    if workflow.enabled:
        service.reschedule(session, workflow, now_utc=now_utc)

    if not workflow.enabled:
        return {"skipped": "workflow_disabled", "workflowId": workflow.id}

    evidence = service.collect_evidence(
        session, workflow, reporting_day, github_reader=github_reader,
    )
    try:
        draft = service.generate_draft(session, workflow, reporting_day)
    except policy.DraftLocked as exc:
        # Already sent or skipped for this day — a duplicate or late job.
        return {"skipped": str(exc), "workflowId": workflow.id}

    included = sum(1 for row in evidence if row.included)
    blockers = sum(1 for row in evidence if row.included and row.activity_type == "blocked")
    record_notification(session, workflow.workspace_id, normalize(
        provider="daypilot",
        event_type="standup.review_due",
        title="Your standup draft is ready",
        summary=(
            f"{included} work signal{'' if included == 1 else 's'} collected"
            + (f" · {blockers} possible blocker{'' if blockers == 1 else 's'}" if blockers else "")
            + f" · review before {workflow.review_time}"
        ),
        severity="info",
        draftId=draft.id,
        workflowId=workflow.id,
        # Deep link: the review lives at its own address precisely so a
        # notification has somewhere to point.
        link="#/standup",
    ))
    return {
        "workflowId": workflow.id,
        "draftId": draft.id,
        "reportingDate": reporting_day.isoformat(),
        "targetStandupDate": draft.target_standup_date,
        "signals": included,
        "nextReviewAt": workflow.next_review_at.isoformat() if workflow.next_review_at else None,
    }


def handle_deliver(
    session: Session,
    payload: dict[str, Any],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Post the approved snapshot into the resolved thread.

    Raises on a thread that cannot be found or a Slack failure, so the queue's
    own backoff retries it — bounded by ``max_attempts``, after which the draft
    is left in a visible failure state with a Retry the user can press.
    """
    workflow = _workflow(session, payload)
    draft = session.get(StandupDraft, str(payload.get("draftId") or ""))
    if draft is None:
        raise LookupError(f"standup draft {payload.get('draftId')!r} not found")
    if not workflow.slack_connection_id:
        raise LookupError("standup workflow has no Slack connection")

    return service.deliver(
        session, workflow, draft,
        send=slack_sender(session, workflow.slack_connection_id),
        read_history=slack_history_reader(session, workflow.slack_connection_id),
        now_utc=now_utc,
    )


def build_handlers(
    session: Session,
    *,
    github_reader: Any = None,
) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    """The handler map for :func:`daypilot_orchestrator.jobs.worker.process_once`.

    The worker's handler signature is ``(payload) -> result`` with no session,
    so the session is bound here. One session per drain keeps the whole pass in
    a single transaction — a crash mid-drain rolls back rather than leaving a
    draft approved with no delivery job.
    """
    return {
        REVIEW_DUE: lambda p: handle_review_due(session, p, github_reader=github_reader),
        DELIVER: lambda p: handle_deliver(session, p),
    }


def bootstrap_schedules(session: Session, workspace_id: str | None = None) -> int:
    """Re-arm any enabled workflow whose next review is missing or in the past.

    Run at worker start. Without it a deployment that was down over a review
    window would never schedule again: the chain is self-perpetuating, so a
    single missed link stops it for good.
    """
    from sqlalchemy import select

    stmt = select(StandupWorkflow).where(StandupWorkflow.enabled.is_(True))
    if workspace_id:
        stmt = stmt.where(StandupWorkflow.workspace_id == workspace_id)

    now = datetime.utcnow()
    rearmed = 0
    for workflow in session.execute(stmt).scalars().all():
        if workflow.next_review_at is not None and workflow.next_review_at > now:
            continue
        service.reschedule(session, workflow)
        rearmed += 1
    session.flush()
    return rearmed
