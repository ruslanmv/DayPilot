"""Multi-agent day planner — graph, agents, service, chat, and revision loop.

Verifies the LangGraph-shaped graph runtime, the optimize-until-good critic
loop, day-shape best practices (deep work morning / meetings afternoon / admin
last / lunch protected), persistence into the existing DayPlan lifecycle,
chat-driven replanning, and the governed self-optimization loop (metrics →
review proposal → approval-gated config version).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import PlanBlock, Task, create_engine_from_settings, session_scope
from daypilot_orchestrator.approvals.center import decide
from daypilot_orchestrator.planner.agents import PlannerConfig, build_planner_graph, classify_kind
from daypilot_orchestrator.planner.graph import END, START, GraphError, StateGraph
from daypilot_orchestrator.planner.revision import active_config, apply_config, review_planner
from daypilot_orchestrator.planner.service import chat_with_plan, generate_plan

client = TestClient(app)
ENGINE = create_engine_from_settings()

TASKS = [
    {"id": "t1", "title": "Implement routing failover", "priority": "high", "projectRisk": "high", "dueToday": True},
    {"id": "t2", "title": "Design eval harness architecture", "priority": "high", "projectRisk": "medium"},
    {"id": "t3", "title": "Client Alpha sync meeting", "priority": "medium"},
    {"id": "t4", "title": "Review GitPilot patch", "priority": "medium"},
    {"id": "t5", "title": "Email triage and expense report", "priority": "low"},
    {"id": "t6", "title": "1:1 with platform team", "priority": "medium"},
]


# --- graph runtime -----------------------------------------------------------

def test_stategraph_runs_nodes_conditionals_and_guards_loops():
    g = StateGraph()
    g.add_node("a", lambda s: {"n": s.get("n", 0) + 1})
    g.add_node("b", lambda s: {"done": True})
    g.add_edge(START, "a")
    g.add_conditional_edges("a", lambda s: "a" if s["n"] < 3 else "b")
    g.add_edge("b", END)
    out = g.compile().invoke({})
    assert out["n"] == 3 and out["done"] is True
    assert out["__path__"] == ["a", "a", "a", "b"]

    # An unbounded loop is stopped by the guard, never hangs.
    loop = StateGraph()
    loop.add_node("x", lambda s: {})
    loop.add_edge(START, "x")
    loop.add_conditional_edges("x", lambda s: "x")
    with pytest.raises(GraphError):
        loop.compile().invoke({})


# --- agents ------------------------------------------------------------------

def test_task_kind_classification():
    assert classify_kind("Implement routing failover") == "deep"
    assert classify_kind("Client Alpha sync meeting") == "meeting"
    assert classify_kind("Email triage") == "admin"
    assert classify_kind("Review GitPilot patch") == "review"


def test_planner_graph_optimizes_the_day_shape():
    result = build_planner_graph().invoke({"tasks": TASKS, "config": PlannerConfig()})
    blocks = result["blocks"]
    by_kind = {}
    for b in blocks:
        by_kind.setdefault(b["kind"], []).append(b)

    # Deep work lands in the morning; meetings after lunch; admin at day end.
    assert all(b["start"] < "12:30" for b in by_kind["deep"][:2])
    assert all(b["start"] >= "13:15" for b in by_kind.get("meeting", []))
    assert all(b["start"] >= "16:00" for b in by_kind.get("admin", []))
    assert any(b["kind"] == "break" for b in blocks)  # lunch is protected

    critique = result["critique"]
    assert critique["score"] >= 60
    assert critique["focusMinutes"] >= 90
    # The critic ran and the graph followed prioritize→schedule→critique(→…)→finalize.
    assert result["__path__"][0] == "prioritize"
    assert result["__path__"][-1] == "finalize"


def test_critic_loop_reruns_scheduler_until_bar_or_cap():
    cfg = PlannerConfig(target_score=101, max_iterations=3)  # unreachable bar
    result = build_planner_graph().invoke({"tasks": TASKS, "config": cfg})
    assert result["iterations"] == 3  # bounded by the cap, then finalized
    assert result["__path__"].count("schedule") == 3


# --- service + chat ----------------------------------------------------------

def _seed_tasks(workspace: str) -> None:
    with session_scope(ENGINE) as s:
        for t in TASKS:
            s.add(Task(workspace_id=workspace, title=t["title"], owner="you",
                       priority=t["priority"], status="active"))


def test_generate_plan_persists_blocks_and_metrics():
    ws = "ws_planner"
    _seed_tasks(ws)
    with session_scope(ENGINE) as s:
        result = generate_plan(s, ws, "2026-07-13")
    assert result["score"] > 0 and result["blocks"]
    assert result["configVersion"] == 1
    with session_scope(ENGINE) as s:
        blocks = s.query(PlanBlock).join(PlanBlock.day_plan).filter_by(workspace_id=ws).count()
    assert blocks == len(result["blocks"])


def test_readiness_reports_real_source_counts():
    ws = "ws_readiness"
    from daypilot_orchestrator.planner.service import planner_readiness
    with session_scope(ENGINE) as s:
        empty = planner_readiness(s, ws, "2026-07-13")
    assert empty["tasksOpen"] == 0 and empty["sufficient"] is False and empty["hasPlan"] is False
    _seed_tasks(ws)
    with session_scope(ENGINE) as s:
        ready = planner_readiness(s, ws, "2026-07-13")
    assert ready["tasksOpen"] == len(TASKS) and ready["sufficient"] is True
    # Gateway route returns the same shape.
    resp = client.get(f"/v1/planner/plans/2026-07-13/readiness?workspaceId={ws}")
    assert resp.status_code == 200 and resp.json()["tasksOpen"] == len(TASKS)


def test_add_task_unblocks_first_plan_readiness():
    """The readiness screen's 'Add your first task' posts to POST /v1/tasks; a
    single created task flips sufficient=false → true so the plan can be built."""
    ws = "ws_readiness_addtask"
    before = client.get(f"/v1/planner/plans/2026-07-14/readiness?workspaceId={ws}").json()
    assert before["tasksOpen"] == 0 and before["sufficient"] is False
    created = client.post("/v1/tasks", json={
        "workspaceId": ws, "title": "Draft the Q3 proposal", "owner": "you",
        "priority": "medium", "status": "active", "source": "planner_setup",
    })
    assert created.status_code == 201
    after = client.get(f"/v1/planner/plans/2026-07-14/readiness?workspaceId={ws}").json()
    assert after["tasksOpen"] == 1 and after["sufficient"] is True


def test_generate_includes_block_type_reason_and_quality():
    ws = "ws_quality"
    _seed_tasks(ws)
    with session_scope(ENGINE) as s:
        result = generate_plan(s, ws, "2026-07-13")
    assert "quality" in result and result["quality"]["label"] in ("Strong", "Balanced", "Needs work")
    # Real, derived per-block type + reason (not invented rationale).
    blk = next(b for b in result["blocks"] if b["kind"] != "break")
    assert blk["type"] in ("focus", "meeting", "admin", "task")
    assert blk["reason"]  # non-empty, built from the block's real facts


def test_read_plan_returns_persisted_blocks_with_kind():
    ws = "ws_read"
    _seed_tasks(ws)
    from daypilot_orchestrator.planner.service import read_plan

    with session_scope(ENGINE) as s:
        generate_plan(s, ws, "2026-07-13")
    with session_scope(ENGINE) as s:
        loaded = read_plan(s, ws, "2026-07-13")
    assert loaded["planDate"] == "2026-07-13"
    assert loaded["blocks"]
    # Kind is re-derived for the UI; lunch is a break, others are work kinds.
    kinds = {b["kind"] for b in loaded["blocks"]}
    assert kinds <= {"deep", "meeting", "admin", "review", "break"}
    assert any(b["kind"] == "break" for b in loaded["blocks"])
    # The gateway GET route returns the same shape.
    resp = client.get(f"/v1/planner/plans/2026-07-13?workspaceId={ws}")
    assert resp.status_code == 200 and resp.json()["blocks"]


def test_chat_answers_and_replans():
    ws = "ws_chat"
    _seed_tasks(ws)
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, "2026-07-13")
    with session_scope(ENGINE) as s:
        answer = chat_with_plan(s, ws, "2026-07-13", "how much focus time do I have?")
    assert answer["replanned"] is False and answer["reply"]
    with session_scope(ENGINE) as s:
        change = chat_with_plan(s, ws, "2026-07-13", "move admin work to the end of the day")
    assert change["replanned"] is True
    assert change["plan"]["score"] > 0


def test_replan_refused_on_wrapped_day():
    ws = "ws_wrapped"
    _seed_tasks(ws)
    with session_scope(ENGINE) as s:
        generate_plan(s, ws, "2026-07-14")
    from daypilot_orchestrator.plan_state import PlanAction
    from daypilot_orchestrator.today_engine import transition_plan
    with session_scope(ENGINE) as s:
        for action in (PlanAction.PROPOSE, PlanAction.APPROVE, PlanAction.ACTIVATE, PlanAction.WRAP):
            transition_plan(s, ws, "2026-07-14", action)
    with session_scope(ENGINE) as s, pytest.raises(ValueError):
        generate_plan(s, ws, "2026-07-14")


# --- self-optimization loop ----------------------------------------------------

def test_review_proposes_tuning_and_apply_is_approval_gated():
    ws = "ws_rev"
    _seed_tasks(ws)
    # Low-focus plans: shrink the day so focus minutes stay under the 180 bar.
    tight = PlannerConfig(day_start="10:30", lunch_start="11:30", day_end="13:00")
    for day in ("2026-07-13", "2026-07-14", "2026-07-15"):
        with session_scope(ENGINE) as s:
            generate_plan(s, ws, day, config=tight)

    with session_scope(ENGINE) as s:
        report = review_planner(s, ws)
    assert report["status"] == "proposal"
    assert report["proposed"]["version"] == 2
    assert any("focus" in f for f in report["findings"])
    approval_id, proposed = report["approvalId"], report["proposed"]

    # Applying before approval is refused.
    with session_scope(ENGINE) as s, pytest.raises(PermissionError):
        apply_config(s, ws, approval_id, proposed)

    # Approve, apply, and the new version becomes active.
    with session_scope(ENGINE) as s:
        decide(s, approval_id, "approve")
    with session_scope(ENGINE) as s:
        applied = apply_config(s, ws, approval_id, proposed)
    assert applied["configVersion"] == 2
    with session_scope(ENGINE) as s:
        assert active_config(s, ws).version == 2


# --- API surface ---------------------------------------------------------------

def test_planner_api_endpoints():
    ws = "ws_api_planner"
    _seed_tasks(ws)
    r = client.post("/v1/planner/plans/2026-07-13/generate", json={"workspaceId": ws})
    assert r.status_code == 200, r.text
    assert r.json()["score"] > 0
    c = client.post("/v1/planner/plans/2026-07-13/chat",
                    json={"workspaceId": ws, "message": "replan and protect my morning"})
    assert c.status_code == 200 and c.json()["replanned"] is True
    cfg = client.get("/v1/planner/config", params={"workspaceId": ws}).json()
    assert cfg["config"]["version"] >= 1
    rev = client.post("/v1/planner/review", json={"workspaceId": ws})
    assert rev.status_code == 200
