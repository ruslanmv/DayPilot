"""Smart plan synchronization + daily review.

Verifies the three-tier model (minor status updates applied automatically;
new tasks / urgent emails produce a *proposal*, never a silent rewrite), the
discard flow ("I'm already on it" — the same suggestion is not re-raised),
proposal apply (real replan), missed-block detection, and the start-of-day
review that auto-builds the plan from real sources.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import EmailItem, Task, create_engine_from_settings, session_scope
from daypilot_orchestrator.planner.service import generate_plan
from daypilot_orchestrator.planner.sync import daily_review, discard_proposal, sync_plan

client = TestClient(app)
ENGINE = create_engine_from_settings()
DATE = "2026-07-14"


def _ws() -> str:
    return "ws-sync-" + uuid.uuid4().hex[:8]


def _seed(ws: str, titles: list[str]) -> None:
    with session_scope(ENGINE) as s:
        for t in titles:
            s.add(Task(workspace_id=ws, title=t, owner="you", priority="high", status="active"))


def test_minor_tier_applies_status_updates_automatically():
    ws = _ws()
    _seed(ws, ["Implement sync engine", "Review sync design"])
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, DATE)
    # Complete one task outside the planner (e.g. from the Tasks view).
    with session_scope(ENGINE) as s:
        task = s.query(Task).filter_by(workspace_id=ws, title="Implement sync engine").one()
        task.status = "done"
    with session_scope(ENGINE) as s:
        result = sync_plan(s, ws, DATE, now="00:01")
    assert result["tier"] == "minor" and result["proposal"] is None
    assert any("completed" in u for u in result["statusUpdates"])


def test_past_scheduled_blocks_become_missed():
    ws = _ws()
    _seed(ws, ["Write integration tests"])
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, DATE)
    with session_scope(ENGINE) as s:
        result = sync_plan(s, ws, DATE, now="23:59")  # end of day: everything passed
    assert any("passed without completion" in u for u in result["statusUpdates"])


def test_new_task_produces_proposal_and_discard_silences_it():
    ws = _ws()
    _seed(ws, ["Original planned work"])
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, DATE)
    # New real work arrives after the plan was generated.
    _seed(ws, ["Urgent client escalation"])
    with session_scope(ENGINE) as s:
        result = sync_plan(s, ws, DATE, now="00:01")
    assert result["tier"] == "medium"
    proposal = result["proposal"]
    assert proposal and "Urgent client escalation" in " ".join(proposal["reasons"])

    # User is already working on it: discard. The plan is kept and the same
    # suggestion is not raised again.
    with session_scope(ENGINE) as s:
        out = discard_proposal(s, ws, DATE, proposal["id"], proposal["signature"])
    assert out["planKept"] is True
    with session_scope(ENGINE) as s:
        again = sync_plan(s, ws, DATE, now="00:01")
    assert again["proposal"] is None


def test_three_new_tasks_escalate_to_major_and_apply_replans():
    ws = _ws()
    _seed(ws, ["Planned work"])
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, DATE)
    _seed(ws, ["New A", "New B", "New C"])
    with session_scope(ENGINE) as s:
        result = sync_plan(s, ws, DATE, now="00:01")
    proposal = result["proposal"]
    assert result["tier"] == "major" and proposal

    # Applying the proposal is a real replan (persisted, new blocks).
    resp = client.post(f"/v1/planner/plans/{DATE}/proposal/apply", json={
        "workspaceId": ws, "proposalId": proposal["id"], "instruction": proposal["instruction"],
    })
    assert resp.status_code == 200 and resp.json()["blocks"]


def test_urgent_email_with_schedule_impact_triggers_proposal():
    ws = _ws()
    _seed(ws, ["Planned work"])
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, DATE)
    with session_scope(ENGINE) as s:
        s.add(EmailItem(
            workspace_id=ws, external_id="9001", subject="Deadline moved to tomorrow",
            sender="pm@example.com", urgency="high",
            classification_json={"scheduleImpact": True},
        ))
    with session_scope(ENGINE) as s:
        result = sync_plan(s, ws, DATE, now="00:01")
    assert result["tier"] == "medium"
    assert result["proposal"] and any("Deadline moved" in r for r in result["proposal"]["reasons"])


def test_daily_review_autobuilds_plan_and_reports_counts():
    ws = _ws()
    _seed(ws, ["Morning deep work", "Team sync meeting", "Email triage"])
    with session_scope(ENGINE) as s:
        review = daily_review(s, ws, DATE, now="00:01")
    assert review["regenerated"] is True and review["blocks"] > 0
    # Second review the same day does not regenerate (plan already exists).
    with session_scope(ENGINE) as s:
        second = daily_review(s, ws, DATE, now="00:01")
    assert second["regenerated"] is False

    # Gateway routes are wired.
    resp = client.post(f"/v1/planner/plans/{DATE}/daily-review", json={"workspaceId": ws, "now": "00:01"})
    assert resp.status_code == 200 and resp.json()["blocks"] > 0
    resp = client.post(f"/v1/planner/plans/{DATE}/sync", json={"workspaceId": ws, "now": "00:01"})
    assert resp.status_code == 200 and resp.json()["hasPlan"] is True


def test_daily_review_on_wrapped_day_degrades_instead_of_500():
    """Regression: a wrapped day made generate_plan raise ValueError inside the
    review, turning the frontend's background poll into an HTTP 500. The review
    must degrade (regenerated=False + honest regenerateError) and still return
    the reconciliation counts."""
    from daypilot_orchestrator.plan_state import PlanState
    from daypilot_orchestrator.today_engine import build_or_get_draft

    ws = _ws()
    _seed(ws, ["Morning deep work"])
    with session_scope(ENGINE) as s:
        plan = build_or_get_draft(s, ws, DATE)
        plan.state = PlanState.WRAPPED.value

    resp = client.post(f"/v1/planner/plans/{DATE}/daily-review", json={"workspaceId": ws, "now": "00:01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["regenerated"] is False
    assert "wrapped" in (body["regenerateError"] or "")
