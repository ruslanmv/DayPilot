"""Planner self-optimization loop (governed).

The planner improves through time without silent self-modification:

1. Every generated plan records metrics (score, focus minutes, switches,
   iterations) as ``planner.metrics`` events.
2. ``review_planner`` aggregates recent metrics, diagnoses weaknesses, and
   proposes a tuned ``PlannerConfig`` — a new *version*, never an in-place edit.
3. The proposal opens an Approval Center item. Only an approved proposal is
   applied, by appending a ``planner.config`` event; ``active_config`` always
   reads the latest applied version. Config history is append-only and auditable.
4. For changes beyond parameters, the review emits a code-review suggestion that
   can be filed as a GitPilot coding run — the same approval-gated path as any
   code change.

Run the review periodically (a Routine/cron hitting ``POST /v1/planner/review``)
so the planner is re-evaluated on real usage and only ever changes with sign-off.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, Event

from .agents import PlannerConfig

CONFIG_EVENT = "planner.config"
METRICS_EVENT = "planner.metrics"


def active_config(session: Session, workspace_id: str = "default") -> PlannerConfig:
    """The latest applied config version (append-only history on the event stream)."""
    row = session.execute(
        select(Event).where(Event.workspace_id == workspace_id, Event.type == CONFIG_EVENT)
        .order_by(Event.seq.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return PlannerConfig()
    return PlannerConfig.from_dict(row.payload_json.get("config", {}))


def record_plan_metrics(
    session: Session, workspace_id: str, plan_date: str,
    critique: dict[str, Any], config: PlannerConfig, iterations: int,
) -> None:
    session.add(Event(workspace_id=workspace_id, type=METRICS_EVENT, payload_json={
        "planDate": plan_date, "score": critique.get("score", 0),
        "focusMinutes": critique.get("focusMinutes", 0),
        "switches": critique.get("switches", 0),
        "coverage": critique.get("coverage", 1.0),
        "iterations": iterations, "configVersion": config.version,
    }))


def _recent_metrics(session: Session, workspace_id: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Event).where(Event.workspace_id == workspace_id, Event.type == METRICS_EVENT)
        .order_by(Event.seq.desc()).limit(limit)
    ).scalars()
    return [r.payload_json for r in rows]


def review_planner(session: Session, workspace_id: str = "default") -> dict[str, Any]:
    """Periodic review: diagnose recent plans and propose a tuned config version.

    The proposal is approval-gated — nothing changes until a human approves."""
    metrics = _recent_metrics(session, workspace_id)
    current = active_config(session, workspace_id)
    if not metrics:
        return {"status": "no_data", "detail": "no plans recorded yet", "configVersion": current.version}

    n = len(metrics)
    avg_score = sum(m.get("score", 0) for m in metrics) / n
    avg_focus = sum(m.get("focusMinutes", 0) for m in metrics) / n
    avg_switches = sum(m.get("switches", 0) for m in metrics) / n
    avg_iters = sum(m.get("iterations", 0) for m in metrics) / n

    proposed = PlannerConfig.from_dict(current.as_dict())
    proposed.version = current.version + 1
    findings: list[str] = []

    if avg_focus < 180:
        proposed.deep_block_minutes = min(current.deep_block_minutes + 15, 120)
        proposed.w_deep_morning = round(current.w_deep_morning + 0.5, 2)
        findings.append(f"avg focus {avg_focus:.0f} min < 180 — lengthen deep blocks, weight deep work higher")
    if avg_switches > 3:
        proposed.c_switches = round(min(current.c_switches + 0.05, 0.4), 2)
        proposed.c_focus = round(max(current.c_focus - 0.05, 0.3), 2)
        findings.append(f"avg {avg_switches:.1f} context switches — penalize switching harder")
    if avg_iters >= current.max_iterations:
        proposed.target_score = max(current.target_score - 5, 60)
        findings.append("critic loop always hits the iteration cap — relax the bar slightly")
    if avg_score >= 90 and current.target_score < 90:
        proposed.target_score = min(current.target_score + 5, 95)
        findings.append(f"avg score {avg_score:.0f} — raise the quality bar")

    if not findings:
        return {"status": "healthy", "avgScore": round(avg_score, 1), "configVersion": current.version}

    approval = Approval(
        workspace_id=workspace_id, action="planner.config.update",
        summary="Planner tuning: " + "; ".join(findings), risk="low", status="pending",
        resource_type="planner_config", resource_id=str(proposed.version),
    )
    session.add(approval)
    session.add(AuditLog(event_type="planner.review", risk="low", decision="recorded", payload_json={
        "avgScore": round(avg_score, 1), "avgFocusMinutes": round(avg_focus, 1),
        "avgSwitches": round(avg_switches, 1), "findings": findings,
        "proposedVersion": proposed.version, "approvalId": None,
    }))
    session.flush()
    return {
        "status": "proposal",
        "findings": findings,
        "avgScore": round(avg_score, 1),
        "avgFocusMinutes": round(avg_focus, 1),
        "current": current.as_dict(),
        "proposed": proposed.as_dict(),
        "approvalId": approval.id,
        "codeReviewSuggestion": (
            "If tuning cannot fix these findings, file a GitPilot coding run against "
            "services/orchestrator/daypilot_orchestrator/planner/agents.py (approval-gated)."
        ),
    }


def apply_config(session: Session, workspace_id: str, approval_id: str,
                 proposed: dict[str, Any]) -> dict[str, Any]:
    """Apply an approved proposal by appending a new config version. Refuses if
    the approval is not granted — the platform decides, not the model."""
    approval = session.get(Approval, approval_id)
    if approval is None or approval.resource_type != "planner_config":
        raise KeyError(approval_id)
    if approval.status != "approved":
        raise PermissionError("planner config change not approved")
    cfg = PlannerConfig.from_dict(proposed)
    session.add(Event(workspace_id=workspace_id, type=CONFIG_EVENT,
                      payload_json={"config": cfg.as_dict(), "approvalId": approval_id}))
    session.add(AuditLog(event_type="planner.config.applied", risk="low", decision="executed",
                         payload_json={"version": cfg.version, "approvalId": approval_id}))
    session.flush()
    return {"status": "applied", "configVersion": cfg.version}
