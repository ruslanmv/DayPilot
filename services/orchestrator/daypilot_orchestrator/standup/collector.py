"""Gather what actually happened, as traceable signals.

The collector never writes prose. It writes rows that each point back at a real
object — a task id, a commit sha, a plan block, a calendar event — so the
review surface can answer "why does it say I did that?" for every bullet.

Collection is idempotent: each signal carries a ``dedupe_key`` derived from the
thing itself, so running the 17:45 pass twice, or re-running it after the user
adds a note, updates rows rather than duplicating the day's work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    AgentRun,
    Approval,
    CalendarEvent,
    CodingRun,
    DayPlan,
    PlanBlock,
    Project,
    StandupEvidence,
    Task,
)

from . import schedule

#: Activity types. These drive which section a signal can feed, so they are a
#: closed set rather than free text.
COMPLETED = "completed"
PROGRESS = "progress"
BLOCKED = "blocked"
PLANNED = "planned"
MEETING = "meeting"

#: Which sources a workflow collects from unless it says otherwise.
DEFAULT_SOURCES = {"daypilot": True, "github": True, "calendar": True, "agents": True}


@dataclass
class Signal:
    """One observed piece of work, before it is persisted."""

    source: str
    activity_type: str
    summary: str
    occurred_at: datetime
    dedupe_key: str
    source_ref: str = ""
    project_id: str | None = None
    project_name: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


#: A GitHub reader is injected rather than imported, so collection stays a pure
#: function of "what the sources returned" and a workspace with no GitHub
#: connection simply contributes nothing.
GitHubReader = Callable[[datetime, datetime], Iterable[dict[str, Any]]]


def _project_names(session: Session, workspace_id: str) -> dict[str, str]:
    rows = session.execute(
        select(Project.id, Project.name).where(Project.workspace_id == workspace_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _in_window(moment: datetime | None, start: datetime, end: datetime) -> bool:
    if moment is None:
        return False
    naive = moment.replace(tzinfo=None) if moment.tzinfo else moment
    return start <= naive <= end


# ---------------------------------------------------------------------------
# Per-source readers
# ---------------------------------------------------------------------------

def _daypilot_signals(
    session: Session, workspace_id: str, start: datetime, end: datetime,
    names: dict[str, str],
) -> list[Signal]:
    """Tasks, plan blocks and approvals — DayPilot's own record of the day."""
    out: list[Signal] = []

    tasks = session.execute(
        select(Task).where(Task.workspace_id == workspace_id)
    ).scalars().all()
    for task in tasks:
        if not _in_window(task.updated_at, start, end):
            continue
        status = (task.status or "").lower()
        if status in {"done", "completed"}:
            activity = COMPLETED
        elif status == "blocked":
            activity = BLOCKED
        elif status in {"active", "in_progress"}:
            activity = PROGRESS
        else:
            continue
        out.append(Signal(
            source="daypilot",
            activity_type=activity,
            summary=task.title,
            occurred_at=task.updated_at,
            dedupe_key=f"task:{task.id}:{status}",
            source_ref=f"task/{task.id}",
            project_id=task.project_id,
            project_name=names.get(task.project_id or "", ""),
            metadata={"priority": task.priority, "status": status,
                      "nextAction": task.next_action or ""},
        ))

    # Plan blocks say what the day was *supposed* to be. A completed block is
    # corroboration; a missed one is honest signal that the plan slipped.
    day_plans = session.execute(
        select(DayPlan).where(DayPlan.workspace_id == workspace_id)
    ).scalars().all()
    plan_ids = {p.id: p for p in day_plans}
    if plan_ids:
        blocks = session.execute(
            select(PlanBlock).where(PlanBlock.day_plan_id.in_(list(plan_ids)))
        ).scalars().all()
        for block in blocks:
            if not _in_window(block.created_at, start, end):
                continue
            status = (block.status or "").lower()
            if status not in {"done", "completed", "missed"}:
                continue
            out.append(Signal(
                source="daypilot",
                activity_type=COMPLETED if status in {"done", "completed"} else PROGRESS,
                summary=block.title,
                occurred_at=block.created_at,
                dedupe_key=f"block:{block.id}:{status}",
                source_ref=f"plan-block/{block.id}",
                confidence=0.9,
                metadata={"planStatus": status},
            ))

    # A pending approval is a blocker by definition: the work is finished and
    # waiting on a person.
    approvals = session.execute(
        select(Approval).where(Approval.workspace_id == workspace_id,
                               Approval.status == "pending")
    ).scalars().all()
    for approval in approvals:
        if not _in_window(approval.created_at, start, end):
            continue
        out.append(Signal(
            source="daypilot",
            activity_type=BLOCKED,
            summary=f"Waiting for approval: {approval.summary or approval.action}",
            occurred_at=approval.created_at,
            dedupe_key=f"approval:{approval.id}",
            source_ref=f"approval/{approval.id}",
            metadata={"risk": approval.risk},
        ))
    return out


def _agent_signals(
    session: Session, workspace_id: str, start: datetime, end: datetime,
    names: dict[str, str],
) -> list[Signal]:
    """Agent and coding runs. A failed run is a blocker, not an achievement."""
    out: list[Signal] = []

    for run in session.execute(
        select(AgentRun).where(AgentRun.workspace_id == workspace_id)
    ).scalars().all():
        if not _in_window(run.updated_at, start, end):
            continue
        state = (run.state or "").lower()
        if state == "succeeded":
            activity, summary = COMPLETED, run.current_work or run.name
        elif state == "failed":
            activity, summary = BLOCKED, f"Agent run failed: {run.name}"
        else:
            continue
        out.append(Signal(
            source="agents",
            activity_type=activity,
            summary=summary,
            occurred_at=run.updated_at,
            dedupe_key=f"agent-run:{run.id}:{state}",
            source_ref=f"agent-run/{run.id}",
            project_id=run.project_id,
            project_name=names.get(run.project_id or "", ""),
            metadata={"state": state, "detail": run.last_error or ""},
        ))

    coding_runs = session.execute(
        select(CodingRun).where(CodingRun.workspace_id == workspace_id)
    ).scalars().all()
    # The run's own task carries the human sentence; the run carries the repo.
    task_titles = {
        row[0]: row[1]
        for row in session.execute(
            select(Task.id, Task.title).where(Task.workspace_id == workspace_id)
        ).all()
    }
    for run in coding_runs:
        if not _in_window(run.updated_at, start, end):
            continue
        status = (run.status or "").lower()
        if status in {"applied", "merged", "completed", "succeeded"}:
            activity = COMPLETED
        elif status in {"failed", "error"}:
            activity = BLOCKED
        else:
            activity = PROGRESS
        title = task_titles.get(run.task_id or "") or run.diff_summary or f"Coding run on {run.repo}"
        out.append(Signal(
            source="github",
            activity_type=activity,
            summary=title,
            occurred_at=run.updated_at,
            dedupe_key=f"coding-run:{run.id}:{status}",
            source_ref=run.pr_url or f"coding-run/{run.id}",
            project_id=run.project_id,
            project_name=names.get(run.project_id or "", "") or run.repo,
            metadata={"status": status, "repo": run.repo, "branch": run.branch or "",
                      "filesChanged": run.files_changed},
        ))
    return out


def _calendar_signals(
    session: Session, workspace_id: str, start: datetime, end: datetime,
) -> list[Signal]:
    """Meetings attended, and tomorrow's fixed commitments."""
    out: list[Signal] = []
    for event in session.execute(
        select(CalendarEvent).where(CalendarEvent.workspace_id == workspace_id)
    ).scalars().all():
        starts = getattr(event, "start_at", None) or getattr(event, "starts_at", None)
        if not _in_window(starts, start, end):
            continue
        out.append(Signal(
            source="calendar",
            activity_type=MEETING,
            summary=getattr(event, "title", "") or "Meeting",
            occurred_at=starts,
            dedupe_key=f"calendar:{event.id}",
            source_ref=f"calendar/{event.id}",
            confidence=0.8,
        ))
    return out


def _github_signals(reader: GitHubReader, start: datetime, end: datetime) -> list[Signal]:
    """Commits, pull requests and CI results from an injected reader."""
    out: list[Signal] = []
    for item in reader(start, end) or []:
        kind = str(item.get("kind") or "commit")
        failed = bool(item.get("failed"))
        out.append(Signal(
            source="github",
            activity_type=BLOCKED if failed else (
                COMPLETED if kind in {"pr_merged", "issue_closed", "commit"} else PROGRESS
            ),
            summary=str(item.get("summary") or ""),
            occurred_at=item.get("occurred_at") or start,
            dedupe_key=f"github:{kind}:{item.get('ref') or item.get('summary')}",
            source_ref=str(item.get("ref") or ""),
            project_name=str(item.get("repo") or ""),
            metadata={"kind": kind, "repo": item.get("repo") or ""},
        ))
    return out


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def collect(
    session: Session,
    workflow: Any,
    reporting_day: date,
    *,
    github_reader: GitHubReader | None = None,
    now_utc: datetime | None = None,
) -> list[StandupEvidence]:
    """Collect and persist the day's evidence. Safe to run repeatedly.

    Returns every evidence row for the day, including ones a previous pass
    stored and the user has since excluded — the exclusion is theirs to keep.
    """
    start, end = schedule.reporting_window(
        timezone_name=workflow.timezone,
        reporting_day=reporting_day,
        days=workflow.working_days,
    )
    sources = {**DEFAULT_SOURCES, **(workflow.evidence_source_config or {})}
    names = _project_names(session, workflow.workspace_id)

    signals: list[Signal] = []
    if sources.get("daypilot", True):
        signals += _daypilot_signals(session, workflow.workspace_id, start, end, names)
    if sources.get("agents", True):
        signals += _agent_signals(session, workflow.workspace_id, start, end, names)
    if sources.get("calendar", True):
        signals += _calendar_signals(session, workflow.workspace_id, start, end)
    if sources.get("github", True) and github_reader is not None:
        signals += _github_signals(github_reader, start, end)

    day_key = reporting_day.isoformat()
    existing = {
        row.dedupe_key: row
        for row in session.execute(
            select(StandupEvidence).where(
                StandupEvidence.workflow_id == workflow.id,
                StandupEvidence.reporting_date == day_key,
            )
        ).scalars()
    }

    for signal in signals:
        row = existing.get(signal.dedupe_key)
        if row is None:
            row = StandupEvidence(
                workspace_id=workflow.workspace_id,
                workflow_id=workflow.id,
                reporting_date=day_key,
                dedupe_key=signal.dedupe_key,
            )
            session.add(row)
            existing[signal.dedupe_key] = row
        # Refresh the facts; never touch `included`, which is the user's call
        # and must survive a re-collect.
        row.source = signal.source
        row.source_ref = signal.source_ref
        row.activity_type = signal.activity_type
        row.summary = signal.summary
        row.project_id = signal.project_id
        row.project_name = signal.project_name
        row.occurred_at = signal.occurred_at
        row.confidence = signal.confidence
        row.metadata_json = signal.metadata

    session.flush()
    return sorted(existing.values(), key=lambda r: (r.occurred_at or datetime.min))


def add_manual_note(
    session: Session, workflow: Any, reporting_day: date, text: str,
    *, occurred_at: datetime | None = None,
) -> StandupEvidence:
    """Work that happened outside every connected system.

    Stored as evidence like anything else so a bullet built from it is still
    traceable — to the user's own words rather than to a commit.
    """
    row = StandupEvidence(
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
        reporting_date=reporting_day.isoformat(),
        source="manual",
        activity_type=COMPLETED,
        summary=text.strip(),
        occurred_at=occurred_at or datetime.utcnow(),
        dedupe_key=f"manual:{workflow.id}:{reporting_day.isoformat()}:{abs(hash(text)) % 10**12}",
        confidence=1.0,
    )
    session.add(row)
    session.flush()
    return row
