"""Tests for the daily plan lifecycle, Focus Mode, wrap-up, and continuity (B4)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.plan_state import (
    InvalidPlanTransition,
    PlanAction,
    PlanState,
    allowed_actions,
    is_terminal,
    next_state,
)

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- State machine (pure) ---------------------------------------------------

def test_happy_path_transitions():
    state = PlanState.DRAFT
    for action in (PlanAction.PROPOSE, PlanAction.APPROVE, PlanAction.ACTIVATE, PlanAction.WRAP):
        state = next_state(state, action)
    assert state is PlanState.WRAPPED
    assert is_terminal(state)
    assert allowed_actions(state) == []


def test_invalid_transition_raises():
    with pytest.raises(InvalidPlanTransition):
        next_state(PlanState.DRAFT, PlanAction.APPROVE)


def test_adjust_round_trips_back_to_approved():
    assert next_state(PlanState.APPROVED, PlanAction.ADJUST) is PlanState.ADJUSTED
    assert next_state(PlanState.ADJUSTED, PlanAction.APPROVE) is PlanState.APPROVED


# --- API lifecycle ----------------------------------------------------------

def test_draft_from_tasks_then_full_lifecycle():
    ws = _ws()
    for i in range(3):
        client.post("/v1/tasks", json={"title": f"T{i}", "workspaceId": ws, "status": "active", "day": "Thursday"})
    date = "2026-07-09"  # Thursday

    draft = client.post(f"/v1/plans/{date}/draft?workspaceId={ws}").json()
    assert draft["state"] == "DRAFT"
    assert len(draft["blocks"]) == 3
    assert draft["allowedActions"] == ["propose"]

    states = []
    for action in ("propose", "approve", "activate", "wrap"):
        resp = client.post(f"/v1/plans/{date}/transition?workspaceId={ws}", json={"action": action})
        assert resp.status_code == 200
        states.append(resp.json()["state"])
    assert states == ["PROPOSED", "APPROVED", "ACTIVE", "WRAPPED"]


def test_api_rejects_invalid_transition_with_409():
    ws = _ws()
    date = "2026-07-09"
    client.post(f"/v1/plans/{date}/draft?workspaceId={ws}")
    resp = client.post(f"/v1/plans/{date}/transition?workspaceId={ws}", json={"action": "approve"})
    assert resp.status_code == 409


def test_focus_mode_returns_context_and_emits_event():
    ws = _ws()
    task = client.post("/v1/tasks", json={"title": "Deep work", "workspaceId": ws, "status": "active"}).json()
    focus = client.post(f"/v1/focus/{task['id']}?workspaceId={ws}").json()
    assert focus["task"]["id"] == task["id"]
    assert focus["allowedActions"] == ["done", "blocked", "hand_to_ai"]

    events = client.get(f"/v1/events?workspaceId={ws}").json()["items"]
    assert any(e["type"] == "block.started" for e in events)


def test_focus_missing_task_404():
    assert client.post("/v1/focus/nope").status_code == 404


def test_wrapup_reports_progress_and_drafts_tomorrow():
    ws = _ws()
    client.post("/v1/tasks", json={"title": "done one", "workspaceId": ws, "status": "done"})
    client.post("/v1/tasks", json={"title": "open one", "workspaceId": ws, "status": "active"})
    date = "2026-07-09"
    wrap = client.get(f"/v1/plans/{date}/wrapup?workspaceId={ws}").json()
    assert wrap["progress"]["tasksTotal"] == 2
    assert wrap["progress"]["tasksDone"] == 1
    assert wrap["tomorrow"]["planDate"] == "2026-07-10"
    assert wrap["tomorrow"]["state"] == "DRAFT"


def test_continuity_lists_projects_risk_first():
    ws = _ws()
    items = client.get(f"/v1/continuity?workspaceId={ws}").json()["items"]
    assert isinstance(items, list)
