"""Continuous plan synchronization + the daily review.

Keeps the published day plan aligned with real work as it changes, using the
industry three-tier model instead of recalculating everything on every event:

    minor   — status-only updates DayPilot applies automatically (a task was
              completed or blocked elsewhere; a scheduled block's time passed).
    medium  — new work arrived (a task created after the plan, an urgent email
              with schedule impact): DayPilot *proposes* an adjustment to the
              remaining day. Nothing moves until the user applies it, and the
              proposal can be discarded ("I'm already on it") — a discarded
              signature is remembered so the same suggestion is not re-raised.
    major   — several new commitments: propose a full recalculation of the day.

The daily review runs when the planner is opened for a new day: it marks past
scheduled blocks as missed (real status, never fabricated progress), counts the
carry-over, and rebuilds the day from real sources when no plan exists yet.
Every pass is recorded on the event stream for audit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import EmailItem, Event, Task

from ..today_engine import build_or_get_draft
from .service import generate_plan, planner_readiness

EVENT_SYNC = "planner.sync"
EVENT_DAILY_REVIEW = "planner.daily_review"
EVENT_PROPOSAL = "planner.proposal"
EVENT_PROPOSAL_APPLIED = "planner.proposal.applied"
EVENT_PROPOSAL_DISCARDED = "planner.proposal.discarded"

OPEN_STATUSES = ("active", "running", "scheduled", "needs_approval")


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> Event:
    event = Event(workspace_id=workspace_id, type=event_type, payload_json=payload)
    session.add(event)
    session.flush()
    return event


def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def _discarded_signatures(session: Session, workspace_id: str) -> set[str]:
    rows = session.execute(
        select(Event)
        .where(Event.workspace_id == workspace_id, Event.type == EVENT_PROPOSAL_DISCARDED)
        .order_by(Event.seq.desc())
        .limit(50)
    ).scalars()
    return {r.payload_json.get("signature", "") for r in rows if r.payload_json}


def sync_plan(
    session: Session, workspace_id: str, plan_date: str, now: str | None = None
) -> dict[str, Any]:
    """One synchronization pass: apply minor status updates, detect new work,
    and (when warranted) return a *proposal* — never a silent plan rewrite."""
    plan = build_or_get_draft(session, workspace_id, plan_date)
    if not plan.blocks:
        return {"planDate": plan_date, "hasPlan": False, "tier": "none",
                "statusUpdates": [], "proposal": None}

    now_hhmm = now or _now_hhmm()
    blocks = sorted(plan.blocks, key=lambda b: b.order_index)
    block_by_task = {b.task_id: b for b in blocks if b.task_id}
    generated_at = max((b.created_at for b in blocks if b.created_at), default=None)

    status_updates: list[str] = []

    # ---- minor tier: reflect real task status onto the plan ------------------
    if block_by_task:
        tasks = session.execute(
            select(Task).where(Task.workspace_id == workspace_id, Task.id.in_(block_by_task))
        ).scalars()
        for t in tasks:
            block = block_by_task[t.id]
            if t.status == "done" and block.status != "done":
                block.status = "done"
                status_updates.append(f"Marked “{block.title}” completed (finished elsewhere).")
            elif t.status == "blocked" and block.status not in ("blocked", "done"):
                block.status = "blocked"
                status_updates.append(f"Marked “{block.title}” blocked.")

    # A scheduled block whose end time has passed without completion is missed —
    # a real state the review can act on, never fabricated progress.
    for b in blocks:
        if b.status == "scheduled" and b.end_time and b.end_time < now_hhmm:
            b.status = "missed"
            status_updates.append(f"“{b.title}” passed without completion.")

    # ---- medium/major tiers: new real work since the plan was generated ------
    open_tasks = session.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.status.in_(OPEN_STATUSES),
            Task.owner == "you",
        )
    ).scalars().all()
    new_tasks = [
        t for t in open_tasks
        if t.id not in block_by_task
        and (generated_at is None or (t.created_at and t.created_at > generated_at))
    ]

    urgent_emails = [
        e for e in session.execute(
            select(EmailItem).where(
                EmailItem.workspace_id == workspace_id,
                EmailItem.urgency.in_(("high", "critical")),
            ).order_by(EmailItem.created_at.desc()).limit(20)
        ).scalars()
        if (generated_at is None or (e.created_at and e.created_at > generated_at))
        and (e.classification_json or {}).get("scheduleImpact")
    ]

    signal_count = len(new_tasks) + len(urgent_emails)
    tier = "minor" if signal_count == 0 else ("major" if len(new_tasks) >= 3 else "medium")

    proposal: dict[str, Any] | None = None
    if signal_count > 0:
        signature = "|".join(sorted([t.id for t in new_tasks] + [e.id for e in urgent_emails]))
        if signature not in _discarded_signatures(session, workspace_id):
            reasons = [f"New task: “{t.title}”" for t in new_tasks[:3]]
            reasons += [f"Urgent email: “{e.subject}” from {e.sender}" for e in urgent_emails[:2]]
            title = (
                "Recalculate today around the new work"
                if tier == "major"
                else "Fit the new work into your remaining day"
            )
            event = _emit(session, workspace_id, EVENT_PROPOSAL, {
                "planDate": plan_date, "tier": tier, "signature": signature,
                "newTasks": len(new_tasks), "urgentEmails": len(urgent_emails),
            })
            proposal = {
                "id": event.id,
                "title": title,
                "tier": tier,
                "reasons": reasons,
                "signature": signature,
                "instruction": "replan the remaining day, keep completed work and protect fixed commitments",
            }

    _emit(session, workspace_id, EVENT_SYNC, {
        "planDate": plan_date, "tier": tier,
        "statusUpdates": len(status_updates),
        "newTasks": len(new_tasks), "urgentEmails": len(urgent_emails),
        "proposed": proposal is not None,
    })
    session.flush()
    return {
        "planDate": plan_date, "hasPlan": True, "tier": tier,
        "statusUpdates": status_updates, "proposal": proposal,
    }


def apply_proposal(
    session: Session, workspace_id: str, plan_date: str, proposal_id: str, instruction: str
) -> dict[str, Any]:
    """User accepted the suggested update: replan (persisted) and record it."""
    result = generate_plan(session, workspace_id, plan_date, instruction=instruction)
    _emit(session, workspace_id, EVENT_PROPOSAL_APPLIED,
          {"planDate": plan_date, "proposalId": proposal_id})
    return result


def discard_proposal(
    session: Session, workspace_id: str, plan_date: str,
    proposal_id: str, signature: str, reason: str = "user_already_working",
) -> dict[str, Any]:
    """User dismissed the suggestion (e.g. already doing the work). The plan is
    kept untouched and the signature is remembered so the same suggestion is
    not raised again."""
    _emit(session, workspace_id, EVENT_PROPOSAL_DISCARDED, {
        "planDate": plan_date, "proposalId": proposal_id,
        "signature": signature, "reason": reason,
    })
    return {"discarded": proposal_id, "planKept": True}


def daily_review(
    session: Session, workspace_id: str, plan_date: str, now: str | None = None
) -> dict[str, Any]:
    """The start-of-day review: reconcile yesterday's leftovers into real
    statuses, and build today's plan automatically when sources are ready."""
    readiness = planner_readiness(session, workspace_id, plan_date)
    plan = build_or_get_draft(session, workspace_id, plan_date)

    # A fresh day may hold the greedy lifecycle draft (build_or_get_draft copies
    # open tasks in). The review runs the multi-agent optimizer once per day —
    # i.e. whenever no *optimized* blocks exist yet — so every working day
    # starts from an optimized, up-to-date plan.
    regenerated = False
    regenerate_error: str | None = None
    has_optimized = any(b.source == "planner" for b in plan.blocks)
    if not has_optimized and readiness["sufficient"]:
        # Regeneration is best-effort: a wrapped day (ValueError) or a planner
        # failure must degrade the review, never turn a background poll into a
        # 500 — the review's job is reconciling statuses either way.
        try:
            generate_plan(session, workspace_id, plan_date)
            regenerated = True
            plan = build_or_get_draft(session, workspace_id, plan_date)
        except ValueError as exc:
            regenerate_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - degrade, don't fail the review
            regenerate_error = f"planner_failed: {type(exc).__name__}"

    sync_result = sync_plan(session, workspace_id, plan_date, now=now)

    blocks = list(plan.blocks)
    done = sum(1 for b in blocks if b.status == "done")
    missed = sum(1 for b in blocks if b.status == "missed")
    _emit(session, workspace_id, EVENT_DAILY_REVIEW, {
        "planDate": plan_date, "regenerated": regenerated,
        "blocks": len(blocks), "done": done, "missed": missed,
    })
    session.flush()
    return {
        "planDate": plan_date,
        "regenerated": regenerated,
        "regenerateError": regenerate_error,
        "blocks": len(blocks),
        "done": done,
        "missed": missed,
        "statusUpdates": sync_result["statusUpdates"],
        "proposal": sync_result["proposal"],
        "readiness": readiness,
    }
