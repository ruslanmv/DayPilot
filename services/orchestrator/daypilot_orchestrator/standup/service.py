"""The standup lifecycle: configure, collect, draft, approve, deliver.

This is the only module that mutates standup rows. It owns the two invariants
that make the feature safe to leave running unattended:

* **Approval freezes text.** ``approve()`` copies the three sections into
  ``approved_*`` and stores their hash. Delivery reads only the frozen copy, so
  an edit made after approval cannot reach Slack — it invalidates the approval
  instead and asks for a fresh one.
* **One reply per day.** ``delivery_key`` is derived from the workflow and the
  standup date, so a retry after a timeout targets the same logical post; a
  draft already ``SENT`` refuses to send again.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AuditLog,
    Event,
    Job,
    StandupDraft,
    StandupEvidence,
    StandupWorkflow,
)

from ..jobs import queue
from . import collector, compiler, policy, schedule
from .thread_resolver import HistoryReader, ResolvedThread, resolve as resolve_thread


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _audit(session: Session, event_type: str, decision: str, payload: dict[str, Any],
           risk: str = "low") -> None:
    session.add(AuditLog(event_type=event_type, risk=risk, decision=decision, payload_json=payload))


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

WORKFLOW_FIELDS = (
    "name", "enabled", "timezone", "working_days", "review_time", "reminder_time",
    "delivery_mode", "slack_connection_id", "slack_channel_id", "slack_channel_name",
    "reminder_signature", "reminder_bot_id", "thread_resolution_mode",
    "evidence_source_config", "approval_policy", "empty_day_policy",
)


def serialize_workflow(row: StandupWorkflow) -> dict[str, Any]:
    return {
        "id": row.id,
        "workspaceId": row.workspace_id,
        "name": row.name,
        "enabled": bool(row.enabled),
        "timezone": row.timezone,
        "workingDays": list(row.working_days or []),
        "reviewTime": row.review_time,
        "reminderTime": row.reminder_time,
        "deliveryMode": row.delivery_mode,
        "slackConnectionId": row.slack_connection_id,
        "slackChannelId": row.slack_channel_id,
        "slackChannelName": row.slack_channel_name,
        "reminderSignature": row.reminder_signature,
        "reminderBotId": row.reminder_bot_id,
        "threadResolutionMode": row.thread_resolution_mode,
        "evidenceSources": {**collector.DEFAULT_SOURCES, **(row.evidence_source_config or {})},
        "approvalPolicy": row.approval_policy,
        "emptyDayPolicy": row.empty_day_policy,
        "nextReviewAt": row.next_review_at.isoformat() if row.next_review_at else None,
    }


#: The shape a brand new workflow starts in. Spelled out rather than left to
#: the column defaults, which SQLAlchemy only applies at flush — validation runs
#: before that, and would otherwise reject its own defaults as ``None``.
NEW_WORKFLOW_DEFAULTS: dict[str, Any] = {
    "name": "Daily Standup",
    "enabled": True,
    "timezone": "UTC",
    "review_time": "18:00",
    "reminder_time": "09:00",
    "delivery_mode": "next_workday",
    "reminder_signature": "Daily Standup Reminder",
    "thread_resolution_mode": "adopt",
    "approval_policy": "always",
    "empty_day_policy": "honest",
    "slack_channel_id": "",
    "slack_channel_name": "",
}


def create_workflow(session: Session, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    row = StandupWorkflow(
        workspace_id=workspace_id,
        working_days=list(schedule.DEFAULT_WORKING_DAYS),
        evidence_source_config=dict(collector.DEFAULT_SOURCES),
        **NEW_WORKFLOW_DEFAULTS,
    )
    _apply(row, body)
    session.add(row)
    session.flush()
    _reschedule(session, row)
    _audit(session, "standup.workflow.created", "recorded",
           {"workflowId": row.id, "channel": row.slack_channel_id, "mode": row.delivery_mode})
    _emit(session, workspace_id, "standup.workflow_created", {"workflowId": row.id})
    return serialize_workflow(row)


def update_workflow(session: Session, workspace_id: str, workflow_id: str,
                    body: dict[str, Any]) -> dict[str, Any] | None:
    row = get_workflow_row(session, workspace_id, workflow_id)
    if row is None:
        return None
    _apply(row, body)
    row.updated_at = datetime.utcnow()
    session.flush()
    _reschedule(session, row)
    _audit(session, "standup.workflow.updated", "recorded",
           {"workflowId": row.id, "fields": sorted(body)})
    return serialize_workflow(row)


def _apply(row: StandupWorkflow, body: dict[str, Any]) -> None:
    """Copy known camelCase fields onto the row, validating the schedule."""
    aliases = {
        "workingDays": "working_days", "reviewTime": "review_time",
        "reminderTime": "reminder_time", "deliveryMode": "delivery_mode",
        "slackConnectionId": "slack_connection_id", "slackChannelId": "slack_channel_id",
        "slackChannelName": "slack_channel_name", "reminderSignature": "reminder_signature",
        "reminderBotId": "reminder_bot_id", "threadResolutionMode": "thread_resolution_mode",
        "evidenceSources": "evidence_source_config", "approvalPolicy": "approval_policy",
        "emptyDayPolicy": "empty_day_policy",
    }
    for key, value in (body or {}).items():
        field = aliases.get(key, key)
        if field not in WORKFLOW_FIELDS or value is None:
            continue
        setattr(row, field, value)
    # Fail loudly at configuration time rather than silently at 18:00.
    schedule.zone(row.timezone)
    schedule.parse_hhmm(row.review_time)
    schedule.parse_hhmm(row.reminder_time)
    row.working_days = schedule.working_days(row.working_days)


def get_workflow_row(session: Session, workspace_id: str, workflow_id: str) -> StandupWorkflow | None:
    row = session.get(StandupWorkflow, workflow_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    return row


def list_workflows(session: Session, workspace_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(StandupWorkflow).where(StandupWorkflow.workspace_id == workspace_id)
        .order_by(StandupWorkflow.created_at.asc())
    ).scalars().all()
    return [serialize_workflow(r) for r in rows]


def _cancel_pending_reviews(session: Session, workflow_id: str) -> int:
    """Drop any review job still waiting for this workflow.

    Rescheduling happens on every edit as well as after each run, so without
    this an afternoon of settings tweaks would leave several review jobs armed
    for the same evening — several drafts, several notifications, one confused
    user.
    """
    rows = session.execute(
        select(Job).where(
            Job.kind == "standup.review_due",
            Job.state == "queued",
        )
    ).scalars().all()
    cancelled = 0
    for job in rows:
        if (job.payload_json or {}).get("workflowId") != workflow_id:
            continue
        job.state = "cancelled"
        job.updated_at = datetime.utcnow()
        cancelled += 1
    return cancelled


def reschedule(session: Session, workflow: StandupWorkflow,
               now_utc: datetime | None = None) -> None:
    """Point the workflow at its next review and enqueue the job for it.

    One occurrence at a time — the job that runs schedules the following one,
    so a timezone or time change takes effect on the next cycle instead of
    leaving a month of stale jobs behind. Exactly one review job is armed at
    any moment.
    """
    _cancel_pending_reviews(session, workflow.id)
    if not workflow.enabled:
        workflow.next_review_at = None
        session.flush()
        return
    occurrence = schedule.next_occurrence(
        timezone_name=workflow.timezone,
        at=workflow.review_time,
        days=workflow.working_days,
        now_utc=now_utc,
    )
    workflow.next_review_at = occurrence.utc
    queue.enqueue(
        session,
        kind="standup.review_due",
        payload={"workflowId": workflow.id, "reportingDate": occurrence.day.isoformat()},
        workspace_id=workflow.workspace_id,
        run_after=occurrence.utc,
    )
    session.flush()


#: Kept so existing callers inside this module read unchanged.
_reschedule = reschedule


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def serialize_draft(row: StandupDraft, *, message: str = "") -> dict[str, Any]:
    return {
        "id": row.id,
        "workflowId": row.workflow_id,
        "reportingDate": row.reporting_date,
        "targetStandupDate": row.target_standup_date,
        "yesterday": row.yesterday_text,
        "today": row.today_text,
        "blockers": row.blockers_text,
        "provenance": row.provenance_json or {},
        "status": row.status,
        "detail": row.detail,
        "contentHash": row.content_hash,
        "approvedAt": row.approved_at.isoformat() if row.approved_at else None,
        "editable": row.status in policy.EDITABLE_STATES,
        "slackThreadTs": row.slack_thread_ts,
        "slackMessageTs": row.slack_message_ts,
        "sentAt": row.sent_at.isoformat() if row.sent_at else None,
        "attempts": row.attempts,
        "slackPreview": message or compiler.render_slack_message(
            row.yesterday_text, row.today_text, row.blockers_text,
        ),
    }


def serialize_evidence(row: StandupEvidence) -> dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "sourceRef": row.source_ref,
        "activityType": row.activity_type,
        "summary": row.summary,
        "projectName": row.project_name,
        "occurredAt": row.occurred_at.isoformat() if row.occurred_at else None,
        "confidence": row.confidence,
        "included": bool(row.included),
        "metadata": row.metadata_json or {},
    }


def get_draft_row(session: Session, workspace_id: str, draft_id: str) -> StandupDraft | None:
    row = session.get(StandupDraft, draft_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    return row


def collect_evidence(
    session: Session, workflow: StandupWorkflow, reporting_day: date,
    *, github_reader: collector.GitHubReader | None = None,
) -> list[StandupEvidence]:
    rows = collector.collect(session, workflow, reporting_day, github_reader=github_reader)
    _emit(session, workflow.workspace_id, "standup.evidence_collected",
          {"workflowId": workflow.id, "reportingDate": reporting_day.isoformat(),
           "count": len(rows)})
    return rows


def generate_draft(
    session: Session, workflow: StandupWorkflow, reporting_day: date,
) -> StandupDraft:
    """Build (or rebuild) the day's draft from current evidence.

    Refuses to overwrite a draft that has already been sent or skipped — that
    day is history. An approved-but-unsent draft *is* regenerated, and loses
    its approval, because the text changed and consent was given to the old one.
    """
    day_key = reporting_day.isoformat()
    row = session.execute(
        select(StandupDraft).where(
            StandupDraft.workflow_id == workflow.id,
            StandupDraft.reporting_date == day_key,
        )
    ).scalar_one_or_none()

    target = schedule.target_standup_day(
        reporting_day=reporting_day,
        delivery_mode=workflow.delivery_mode,
        days=workflow.working_days,
    )
    if row is None:
        row = StandupDraft(
            workspace_id=workflow.workspace_id,
            workflow_id=workflow.id,
            reporting_date=day_key,
            target_standup_date=target.isoformat(),
            delivery_key=policy.delivery_key(workflow.id, target.isoformat()),
        )
        session.add(row)
    elif row.status in policy.TERMINAL_STATES:
        raise policy.DraftLocked(f"draft for {day_key} is {row.status}")

    evidence = session.execute(
        select(StandupEvidence).where(
            StandupEvidence.workflow_id == workflow.id,
            StandupEvidence.reporting_date == day_key,
        )
    ).scalars().all()

    compiled = compiler.compile_draft(evidence, empty_day_policy=workflow.empty_day_policy)
    row.yesterday_text = compiler.render_section(compiled.yesterday)
    row.today_text = compiler.render_section(compiled.today)
    row.blockers_text = compiler.render_section(compiled.blockers)
    row.provenance_json = compiled.provenance()
    row.target_standup_date = target.isoformat()
    row.delivery_key = policy.delivery_key(workflow.id, target.isoformat())
    _clear_approval(row, reason="regenerated from activity")
    row.status = policy.NEEDS_REVIEW
    row.updated_at = datetime.utcnow()
    session.flush()

    _emit(session, workflow.workspace_id, "standup.draft_ready",
          {"workflowId": workflow.id, "draftId": row.id, "reportingDate": day_key,
           "targetStandupDate": row.target_standup_date,
           "evidenceCount": sum(1 for e in evidence if e.included)})
    return row


def _clear_approval(row: StandupDraft, *, reason: str) -> None:
    """Consent applies to the text that was consented to, and nothing else."""
    if row.content_hash is None and row.approved_at is None:
        return
    row.approved_yesterday = None
    row.approved_today = None
    row.approved_blockers = None
    row.content_hash = None
    row.approved_at = None
    row.approved_by = None
    row.detail = f"Approval cleared: {reason}."


def edit_draft(session: Session, row: StandupDraft, body: dict[str, Any]) -> StandupDraft:
    """Edit any of the three sections.

    An edit to an approved draft is allowed, and revokes the approval — the
    alternative (silently sending text nobody approved) is the thing this whole
    module exists to prevent.
    """
    if row.status in policy.TERMINAL_STATES:
        raise policy.DraftLocked(f"draft is {row.status}")
    changed = False
    for key, field in (("yesterday", "yesterday_text"), ("today", "today_text"),
                       ("blockers", "blockers_text")):
        if key in body and body[key] is not None and getattr(row, field) != body[key]:
            setattr(row, field, str(body[key]))
            changed = True
    if changed:
        _clear_approval(row, reason="content edited after approval")
        row.status = policy.NEEDS_REVIEW
        row.updated_at = datetime.utcnow()
        session.flush()
    return row


def set_evidence_included(
    session: Session, workspace_id: str, evidence_id: str, included: bool,
) -> StandupEvidence | None:
    row = session.get(StandupEvidence, evidence_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    row.included = included
    session.flush()
    return row


def approve(
    session: Session, workflow: StandupWorkflow, row: StandupDraft, *, approved_by: str = "",
    now_utc: datetime | None = None,
) -> StandupDraft:
    """Freeze the exact text and schedule its delivery.

    Everything after this point reads ``approved_*``. The editable fields may
    keep changing; what was consented to cannot.
    """
    if row.status in policy.TERMINAL_STATES:
        raise policy.DraftLocked(f"draft is {row.status}")

    row.approved_yesterday = row.yesterday_text
    row.approved_today = row.today_text
    row.approved_blockers = row.blockers_text
    row.content_hash = policy.content_hash(
        row.yesterday_text, row.today_text, row.blockers_text,
    )
    row.approved_at = now_utc or datetime.utcnow()
    row.approved_by = approved_by or None
    row.status = policy.WAITING_FOR_THREAD
    row.detail = ""

    target = date.fromisoformat(row.target_standup_date)
    if workflow.delivery_mode == "same_day":
        run_after = row.approved_at
    else:
        opens, _closes = schedule.thread_search_window(
            timezone_name=workflow.timezone,
            standup_day=target,
            reminder_time=workflow.reminder_time,
        )
        run_after = opens
    job = queue.enqueue(
        session,
        kind="standup.deliver",
        payload={"workflowId": workflow.id, "draftId": row.id,
                 "deliveryKey": row.delivery_key},
        workspace_id=workflow.workspace_id,
        run_after=run_after,
        max_attempts=5,
    )
    row.delivery_job_id = job.id
    session.flush()

    _audit(session, "standup.draft.approved", "approved",
           {"draftId": row.id, "workflowId": workflow.id,
            "contentHash": row.content_hash, "targetStandupDate": row.target_standup_date},
           risk="medium")
    _emit(session, workflow.workspace_id, "standup.approved",
          {"draftId": row.id, "targetStandupDate": row.target_standup_date,
           "deliverAfter": run_after.isoformat()})
    return row


def skip(session: Session, row: StandupDraft, *, reason: str = "") -> StandupDraft:
    if row.status in policy.TERMINAL_STATES:
        raise policy.DraftLocked(f"draft is {row.status}")
    if row.delivery_job_id:
        queue.cancel(session, row.delivery_job_id)
    row.status = policy.SKIPPED
    row.detail = reason or "Skipped by the user."
    session.flush()
    _audit(session, "standup.draft.skipped", "recorded", {"draftId": row.id, "reason": reason})
    return row


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

#: Sends the approved text. Injected so delivery can be driven by the
#: Integration Gateway in production and by a stub in tests, and so this module
#: never holds a Slack token.
Sender = Callable[[dict[str, Any]], dict[str, Any]]


def deliver(
    session: Session,
    workflow: StandupWorkflow,
    row: StandupDraft,
    *,
    send: Sender,
    read_history: HistoryReader | None = None,
    known_thread_ts: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Resolve the thread and post the approved snapshot, exactly once."""
    if row.status == policy.SENT:
        # A retry that arrives after a successful send. Report the original.
        return {"status": policy.SENT, "messageTs": row.slack_message_ts, "duplicate": True}
    if row.status in {policy.SKIPPED, policy.EXPIRED}:
        raise policy.DraftLocked(f"draft is {row.status}")
    if not row.content_hash or row.approved_yesterday is None:
        raise policy.ApprovalRequired("draft has no approved snapshot")

    # The frozen copy is the only thing that may be sent, and it must still
    # hash to what was approved.
    expected = policy.content_hash(
        row.approved_yesterday, row.approved_today or "", row.approved_blockers or "",
    )
    if expected != row.content_hash:
        row.status = policy.NEEDS_REVIEW
        _clear_approval(row, reason="approved snapshot failed its integrity check")
        session.flush()
        raise policy.ApprovalRequired("approved snapshot does not match its hash")

    target = date.fromisoformat(row.target_standup_date)
    row.attempts += 1

    try:
        thread = _resolve(
            workflow, target,
            read_history=read_history,
            known_thread_ts=known_thread_ts or row.slack_thread_ts,
        )
    except policy.ThreadNotFound as exc:
        row.status = policy.THREAD_NOT_FOUND
        row.detail = str(exc)
        session.flush()
        _emit(session, workflow.workspace_id, "standup.thread_not_found",
              {"draftId": row.id, "targetStandupDate": row.target_standup_date})
        _audit(session, "standup.deliver.no_thread", "blocked",
               {"draftId": row.id, "channel": workflow.slack_channel_id})
        raise

    row.slack_thread_ts = thread.ts
    row.status = policy.SENDING
    session.flush()

    text = compiler.render_slack_message(
        row.approved_yesterday, row.approved_today or "", row.approved_blockers or "",
    )
    try:
        result = send({
            "channel": workflow.slack_channel_id,
            "text": text,
            "threadTs": thread.ts,
            "clientMessageId": row.delivery_key,
        })
    except Exception as exc:  # noqa: BLE001 - surfaced as a visible failure state
        row.status = policy.SEND_FAILED
        row.detail = str(exc)[:2000]
        session.flush()
        _emit(session, workflow.workspace_id, "standup.send_failed",
              {"draftId": row.id, "attempts": row.attempts})
        _audit(session, "standup.deliver.failed", "failed",
               {"draftId": row.id, "attempts": row.attempts}, risk="medium")
        raise

    row.slack_message_ts = str(result.get("ts") or "")
    row.sent_at = now_utc or datetime.utcnow()
    row.status = policy.SENT
    row.detail = ""
    session.flush()

    _audit(session, "standup.deliver.sent", "executed",
           {"draftId": row.id, "threadTs": thread.ts, "messageTs": row.slack_message_ts,
            "deliveryKey": row.delivery_key, "contentHash": row.content_hash}, risk="medium")
    _emit(session, workflow.workspace_id, "standup.sent",
          {"draftId": row.id, "threadTs": thread.ts, "messageTs": row.slack_message_ts})
    return {"status": policy.SENT, "messageTs": row.slack_message_ts,
            "threadTs": thread.ts, "duplicate": False}


def _resolve(
    workflow: StandupWorkflow, target: date, *,
    read_history: HistoryReader | None, known_thread_ts: str | None,
) -> ResolvedThread:
    if known_thread_ts:
        return ResolvedThread(ts=known_thread_ts, text="", matched_on=["known"])
    if read_history is None:
        raise policy.ThreadNotFound("no Slack history reader available")
    return resolve_thread(
        read_history=read_history,
        channel_id=workflow.slack_channel_id,
        standup_day=target,
        timezone_name=workflow.timezone,
        reminder_time=workflow.reminder_time,
        signature=workflow.reminder_signature,
        bot_id=workflow.reminder_bot_id,
    )


def expire_stale(session: Session, workspace_id: str, *, now_utc: datetime | None = None) -> int:
    """Retire drafts whose standup day has passed without delivery.

    Posting Tuesday's update on Thursday is not helpful, so an undelivered
    draft is closed out honestly rather than left waiting forever.
    """
    now = now_utc or datetime.utcnow()
    today = now.date().isoformat()
    rows = session.execute(
        select(StandupDraft).where(
            StandupDraft.workspace_id == workspace_id,
            StandupDraft.status.in_([
                policy.WAITING_FOR_THREAD, policy.THREAD_NOT_FOUND, policy.SEND_FAILED,
            ]),
            StandupDraft.target_standup_date < today,
        )
    ).scalars().all()
    for row in rows:
        row.status = policy.EXPIRED
        row.detail = "The standup day passed before this update could be delivered."
        if row.delivery_job_id:
            queue.cancel(session, row.delivery_job_id)
    session.flush()
    return len(rows)
