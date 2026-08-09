"""Daily Standup Copilot API.

Thin over :mod:`daypilot_orchestrator.standup.service` — the router validates
input, maps refusals to status codes, and never contains a lifecycle rule of
its own. The rules that matter (approval freezes text, one reply per day, never
post outside a thread) live in the engine so every caller gets them.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import StandupDraft, StandupEvidence
from daypilot_orchestrator.standup import policy, service
from daypilot_orchestrator.standup.collector import add_manual_note
from daypilot_orchestrator.standup.delivery import slack_history_reader, slack_sender
from daypilot_orchestrator.standup.thread_resolver import describe_for_setup
from daypilot_orchestrator.standup.thread_resolver import resolve as resolve_thread

from ..db import get_session

router = APIRouter(prefix="/v1/standup", tags=["standup"])


class WorkflowBody(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    timezone: str | None = None
    workingDays: list[int] | None = None
    reviewTime: str | None = None
    reminderTime: str | None = None
    deliveryMode: str | None = None
    slackConnectionId: str | None = None
    slackChannelId: str | None = None
    slackChannelName: str | None = None
    reminderSignature: str | None = None
    reminderBotId: str | None = None
    threadResolutionMode: str | None = None
    evidenceSources: dict[str, bool] | None = None
    approvalPolicy: str | None = None
    emptyDayPolicy: str | None = None


class DraftBody(BaseModel):
    yesterday: str | None = None
    today: str | None = None
    blockers: str | None = None


class NoteBody(BaseModel):
    text: str
    reportingDate: str | None = None


class SkipBody(BaseModel):
    reason: str = ""


def _workflow(session: Session, workspace_id: str, workflow_id: str):
    row = service.get_workflow_row(session, workspace_id, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return row


def _draft(session: Session, workspace_id: str, draft_id: str) -> StandupDraft:
    row = service.get_draft_row(session, workspace_id, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return row


def _day(value: str | None) -> date:
    if not value:
        return datetime.utcnow().date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_date") from exc


# ---- workflows --------------------------------------------------------------

@router.get("/workflows")
def list_workflows(workspaceId: str = "default",
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    return {"workflows": service.list_workflows(session, workspaceId)}


@router.post("/workflows", status_code=201)
def create_workflow(body: WorkflowBody, workspaceId: str = "default",
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return service.create_workflow(session, workspaceId, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, workspaceId: str = "default",
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    return service.serialize_workflow(_workflow(session, workspaceId, workflow_id))


@router.patch("/workflows/{workflow_id}")
def patch_workflow(workflow_id: str, body: WorkflowBody, workspaceId: str = "default",
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        out = service.update_workflow(
            session, workspaceId, workflow_id, body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return out


@router.post("/workflows/{workflow_id}/test-thread-resolution")
def test_thread_resolution(workflow_id: str, workspaceId: str = "default",
                           session: Session = Depends(get_session)) -> dict[str, Any]:
    """Show the user the real message DayPilot would reply under.

    Setup confirms a match once against live Slack, so a wrong channel or a
    reworded reminder is found here rather than discovered by a post landing
    somewhere embarrassing.
    """
    workflow = _workflow(session, workspaceId, workflow_id)
    if not workflow.slack_connection_id or not workflow.slack_channel_id:
        raise HTTPException(status_code=400, detail="slack_not_configured")
    try:
        thread = resolve_thread(
            read_history=slack_history_reader(session, workflow.slack_connection_id),
            channel_id=workflow.slack_channel_id,
            standup_day=datetime.utcnow().date(),
            timezone_name=workflow.timezone,
            reminder_time=workflow.reminder_time,
            signature=workflow.reminder_signature,
            bot_id=workflow.reminder_bot_id,
        )
    except policy.ThreadNotFound as exc:
        return {"found": False, "reason": str(exc),
                "channelName": workflow.slack_channel_name}
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Remember who posts it, so tomorrow's match does not rest on wording alone.
    if thread.bot_id and not workflow.reminder_bot_id:
        workflow.reminder_bot_id = thread.bot_id
        session.flush()
    return describe_for_setup(thread, workflow.slack_channel_name or workflow.slack_channel_id)


@router.post("/workflows/{workflow_id}/collect")
def collect(workflow_id: str, reportingDate: str | None = None, workspaceId: str = "default",
            session: Session = Depends(get_session)) -> dict[str, Any]:
    workflow = _workflow(session, workspaceId, workflow_id)
    rows = service.collect_evidence(session, workflow, _day(reportingDate))
    return {
        "reportingDate": _day(reportingDate).isoformat(),
        "collected": len(rows),
        "included": sum(1 for r in rows if r.included),
        "evidence": [service.serialize_evidence(r) for r in rows],
    }


@router.post("/workflows/{workflow_id}/generate")
def generate(workflow_id: str, reportingDate: str | None = None, workspaceId: str = "default",
             session: Session = Depends(get_session)) -> dict[str, Any]:
    workflow = _workflow(session, workspaceId, workflow_id)
    try:
        row = service.generate_draft(session, workflow, _day(reportingDate))
    except policy.DraftLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.serialize_draft(row)


@router.post("/workflows/{workflow_id}/notes")
def add_note(workflow_id: str, body: NoteBody, workspaceId: str = "default",
             session: Session = Depends(get_session)) -> dict[str, Any]:
    """Record work that happened outside every connected system."""
    workflow = _workflow(session, workspaceId, workflow_id)
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="empty_note")
    row = add_manual_note(session, workflow, _day(body.reportingDate), body.text)
    return service.serialize_evidence(row)


# ---- drafts -----------------------------------------------------------------

@router.get("/drafts/{reporting_date}")
def get_draft_for_date(reporting_date: str, workflowId: str | None = None,
                       workspaceId: str = "default",
                       session: Session = Depends(get_session)) -> dict[str, Any]:
    day = _day(reporting_date)
    stmt = select(StandupDraft).where(
        StandupDraft.workspace_id == workspaceId,
        StandupDraft.reporting_date == day.isoformat(),
    )
    if workflowId:
        stmt = stmt.where(StandupDraft.workflow_id == workflowId)
    row = session.execute(stmt.order_by(StandupDraft.created_at.desc())).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return service.serialize_draft(row)


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: str, body: DraftBody, workspaceId: str = "default",
                session: Session = Depends(get_session)) -> dict[str, Any]:
    row = _draft(session, workspaceId, draft_id)
    try:
        row = service.edit_draft(session, row, body.model_dump(exclude_none=True))
    except policy.DraftLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.serialize_draft(row)


@router.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, workspaceId: str = "default",
                  session: Session = Depends(get_session)) -> dict[str, Any]:
    row = _draft(session, workspaceId, draft_id)
    workflow = _workflow(session, workspaceId, row.workflow_id)
    try:
        row = service.approve(session, workflow, row)
    except policy.DraftLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.serialize_draft(row)


@router.post("/drafts/{draft_id}/skip")
def skip_draft(draft_id: str, body: SkipBody | None = None, workspaceId: str = "default",
               session: Session = Depends(get_session)) -> dict[str, Any]:
    row = _draft(session, workspaceId, draft_id)
    try:
        row = service.skip(session, row, reason=(body.reason if body else ""))
    except policy.DraftLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return service.serialize_draft(row)


@router.post("/drafts/{draft_id}/send-now")
def send_now(draft_id: str, workspaceId: str = "default",
             session: Session = Depends(get_session)) -> dict[str, Any]:
    """Deliver immediately — the retry the user reaches for when a send failed.

    Still refuses without an approved snapshot, and still refuses to post
    outside a thread. "Send now" changes the timing, never the guarantees.
    """
    row = _draft(session, workspaceId, draft_id)
    workflow = _workflow(session, workspaceId, row.workflow_id)
    if not workflow.slack_connection_id:
        raise HTTPException(status_code=400, detail="slack_not_configured")
    try:
        result = service.deliver(
            session, workflow, row,
            send=slack_sender(session, workflow.slack_connection_id),
            read_history=slack_history_reader(session, workflow.slack_connection_id),
        )
    except policy.ApprovalRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except policy.ThreadNotFound as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except policy.DraftLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - a Slack outage is a 502, not a 500
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {**result, "draft": service.serialize_draft(row)}


# ---- evidence ---------------------------------------------------------------

@router.get("/drafts/{draft_id}/evidence")
def draft_evidence(draft_id: str, workspaceId: str = "default",
                   session: Session = Depends(get_session)) -> dict[str, Any]:
    row = _draft(session, workspaceId, draft_id)
    rows = session.execute(
        select(StandupEvidence).where(
            StandupEvidence.workflow_id == row.workflow_id,
            StandupEvidence.reporting_date == row.reporting_date,
        ).order_by(StandupEvidence.occurred_at.asc())
    ).scalars().all()
    return {"evidence": [service.serialize_evidence(r) for r in rows]}


@router.post("/drafts/{draft_id}/evidence/{evidence_id}/include")
def include_evidence(draft_id: str, evidence_id: str, workspaceId: str = "default",
                     session: Session = Depends(get_session)) -> dict[str, Any]:
    return _set_included(session, workspaceId, draft_id, evidence_id, True)


@router.post("/drafts/{draft_id}/evidence/{evidence_id}/exclude")
def exclude_evidence(draft_id: str, evidence_id: str, workspaceId: str = "default",
                     session: Session = Depends(get_session)) -> dict[str, Any]:
    return _set_included(session, workspaceId, draft_id, evidence_id, False)


def _set_included(session: Session, workspace_id: str, draft_id: str,
                  evidence_id: str, included: bool) -> dict[str, Any]:
    _draft(session, workspace_id, draft_id)
    row = service.set_evidence_included(session, workspace_id, evidence_id, included)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence_not_found")
    return service.serialize_evidence(row)


# ---- home surface -----------------------------------------------------------

@router.get("/status")
def status(workspaceId: str = "default",
           session: Session = Depends(get_session)) -> dict[str, Any]:
    """What the Home dashboard card needs, in one call.

    Returns the enabled workflow, today's draft if there is one, and the signal
    counts the pre-review nudge shows at 17:30.
    """
    workflows = service.list_workflows(session, workspaceId)
    active = next((w for w in workflows if w["enabled"]), None)
    if active is None:
        return {"configured": False, "workflows": workflows}

    today = datetime.utcnow().date().isoformat()
    draft = session.execute(
        select(StandupDraft).where(
            StandupDraft.workflow_id == active["id"],
            StandupDraft.reporting_date == today,
        )
    ).scalar_one_or_none()
    evidence = session.execute(
        select(StandupEvidence).where(
            StandupEvidence.workflow_id == active["id"],
            StandupEvidence.reporting_date == today,
        )
    ).scalars().all()
    included = [e for e in evidence if e.included]
    return {
        "configured": True,
        "workflow": active,
        "reportingDate": today,
        "signals": len(included),
        "projects": len({e.project_name for e in included if e.project_name}),
        "possibleBlockers": sum(1 for e in included if e.activity_type == "blocked"),
        "draft": service.serialize_draft(draft) if draft is not None else None,
    }
