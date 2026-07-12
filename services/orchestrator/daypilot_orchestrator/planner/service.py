"""Planner service: run the multi-agent graph and persist the result.

Bridges the planning graph to DayPilot's existing plan lifecycle: the optimized
blocks are written to the same ``DayPlan``/``PlanBlock`` tables the rest of the
app (Focus Mode, wrap-up, continuity) already uses, so the planner is a drop-in
brain upgrade, not a parallel system. Replanning is non-destructive: it rewrites
the day's blocks and records why, but never touches a WRAPPED plan and keeps the
approval lifecycle intact.
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Event, PlanBlock, Project, Task

from ..plan_state import PlanState
from ..today_engine import EVENT_PLAN_UPDATED, build_or_get_draft
from .agents import PlannerConfig, build_planner_graph
from .revision import active_config, record_plan_metrics


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _collect_tasks(session: Session, workspace_id: str) -> list[dict[str, Any]]:
    """Context agent input: open tasks joined with their project's risk."""
    risk_by_project = {
        p.id: p.risk for p in session.execute(
            select(Project).where(Project.workspace_id == workspace_id)
        ).scalars()
    }
    tasks = session.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.status.in_(("active", "running", "scheduled", "needs_approval")),
            Task.owner == "you",
        ).order_by(Task.priority.desc(), Task.created_at.asc()).limit(16)
    ).scalars()
    return [
        {
            "id": t.id, "title": t.title, "priority": t.priority or "medium",
            "owner": t.owner, "dueToday": bool(t.due_date), "projectId": t.project_id,
            "projectRisk": risk_by_project.get(t.project_id, "low"),
        }
        for t in tasks
    ]


def _ollabridge_narrative(blocks: list[dict[str, Any]], critique: dict[str, Any]) -> str | None:
    """Ask the paired Ollabridge model for the plan narrative. Never raises;
    returns None (deterministic fallback) when no provider is reachable."""
    if os.getenv("DAYPILOT_MODEL_BACKEND", "mock") != "ollabridge":
        return None
    try:
        from daypilot_models.ollabridge_client import connector_from_env

        connector = connector_from_env()
        reachable, _, _ = connector.ping()
        if not reachable:
            return None
        agenda = "; ".join(f"{b['start']} {b['title']}" for b in blocks[:8])
        result = connector.generate(
            f"Summarize this optimized engineer day plan in two calm sentences: {agenda}. "
            f"Focus minutes: {critique.get('focusMinutes')}. Score: {critique.get('score')}/100.",
            task="planner",
        )
        text = (result.get("text") or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 - narrative is best-effort, plan must not fail
        return None


def generate_plan(
    session: Session,
    workspace_id: str,
    plan_date: str,
    instruction: str | None = None,
    config: PlannerConfig | None = None,
) -> dict[str, Any]:
    """Run the multi-agent planner and persist the optimized blocks."""
    plan = build_or_get_draft(session, workspace_id, plan_date)
    if plan.state == PlanState.WRAPPED.value:
        raise ValueError("cannot replan a wrapped day")

    cfg = config or active_config(session, workspace_id)
    state: dict[str, Any] = {
        "workspace_id": workspace_id,
        "plan_date": plan_date,
        "tasks": _collect_tasks(session, workspace_id),
        "config": cfg,
        "hints": _hints_from_instruction(instruction),
    }
    result = build_planner_graph().invoke(state)
    blocks = result.get("blocks", [])
    critique = result.get("critique", {})
    narrative = _ollabridge_narrative(blocks, critique) or result.get("narrative", "")

    # Rewrite the day's blocks (non-destructive to the plan record + lifecycle).
    for old in list(plan.blocks):
        session.delete(old)
    session.flush()
    for i, b in enumerate(blocks):
        session.add(PlanBlock(
            day_plan_id=plan.id, task_id=b.get("taskId"), title=b["title"],
            start_time=b["start"], end_time=b["end"], owner=b.get("owner", "you"),
            source="planner", status="scheduled", order_index=i,
        ))
    plan.summary = narrative
    _emit(session, workspace_id, EVENT_PLAN_UPDATED,
          {"planDate": plan_date, "state": plan.state, "blocks": len(blocks),
           "score": critique.get("score"), "planner": "multi-agent", "configVersion": cfg.version})
    record_plan_metrics(session, workspace_id, plan_date, critique, cfg,
                        iterations=result.get("iterations", 0))
    session.flush()
    return {
        "planDate": plan_date,
        "state": plan.state,
        "summary": narrative,
        "score": critique.get("score", 0),
        "critique": critique,
        "iterations": result.get("iterations", 0),
        "configVersion": cfg.version,
        "path": result.get("__path__", []),
        "blocks": blocks,
    }


def _kind_of(title: str, source: str) -> str:
    """Re-derive a block's kind for the UI (PlanBlock persists title, not kind)."""
    from .agents import classify_kind
    if "lunch" in title.lower() or source == "break":
        return "break"
    return classify_kind(title)


def read_plan(session: Session, workspace_id: str, plan_date: str) -> dict[str, Any]:
    """Load the persisted plan for a day without regenerating it.

    Returns the current DayPlan blocks (kind re-derived) so the Planning surface
    can render live, persisted state on load rather than a fabricated timeline.
    """
    plan = build_or_get_draft(session, workspace_id, plan_date)
    blocks = sorted(plan.blocks, key=lambda b: b.order_index)
    return {
        "planDate": plan_date,
        "state": plan.state,
        "summary": plan.summary or "",
        "blocks": [
            {
                "id": b.id,
                "taskId": b.task_id,
                "title": b.title,
                "kind": _kind_of(b.title, b.source),
                "start": b.start_time,
                "end": b.end_time,
                "owner": b.owner,
                "status": b.status,
            }
            for b in blocks
        ],
    }


def _hints_from_instruction(instruction: str | None) -> list[str]:
    """Translate a natural replan instruction into scheduler hints."""
    if not instruction:
        return []
    lowered = instruction.lower()
    hints = []
    if "admin" in lowered and ("afternoon" in lowered or "later" in lowered or "end" in lowered):
        hints.append("batch_admin")
    if "focus" in lowered or "deep" in lowered or "morning" in lowered:
        hints.append("protect_morning")
    return hints


def chat_with_plan(session: Session, workspace_id: str, plan_date: str, message: str) -> dict[str, Any]:
    """Conversational interface to the day plan. Questions are answered from the
    plan; change requests trigger a replan with the derived hints."""
    lowered = message.lower()
    wants_change = any(k in lowered for k in ("move", "replan", "push", "batch", "protect", "reschedule", "swap"))
    if wants_change:
        result = generate_plan(session, workspace_id, plan_date, instruction=message)
        return {
            "reply": (
                f"Done — I replanned your day. New score {result['score']}/100 with "
                f"{result['critique'].get('focusMinutes', 0)} focused minutes. {result['summary']}"
            ),
            "replanned": True,
            "plan": result,
        }
    plan = build_or_get_draft(session, workspace_id, plan_date)
    blocks = sorted(plan.blocks, key=lambda b: b.order_index)
    if "focus" in lowered or "deep" in lowered:
        deep = [b for b in blocks if b.source == "planner" and "lunch" not in b.title.lower()]
        reply = f"You have {len(deep)} scheduled blocks; deep work is protected in the morning."
    elif "next" in lowered or "now" in lowered:
        nxt = blocks[0].title if blocks else "nothing scheduled"
        reply = f"Next up: {nxt}."
    else:
        reply = plan.summary or "Your plan is ready. Ask me to move things or protect focus time."
    return {"reply": reply, "replanned": False}
