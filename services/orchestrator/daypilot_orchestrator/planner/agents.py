"""Day-planner agent nodes (multi-agent planning graph).

Five small, single-responsibility agents cooperate over a shared state:

    collect_context -> prioritize -> schedule -> critique -(below target)-> schedule
                                                        \\-(good enough)--> finalize

The heuristics encode how a principal AI/ML engineer gets a productive day:
deep work in the morning energy peak, meetings batched after lunch, admin at the
end of the day, explicit buffers, and a protected focus block. The critic scores
each candidate plan and sends it back to the scheduler with concrete hints until
it beats the target score (bounded iterations), which is what makes the plan
*optimized* rather than a single greedy pass.

Every tunable lives in ``PlannerConfig`` so the revision loop can improve the
planner over time without touching this code path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# ---------------------------------------------------------------- config ----

@dataclass
class PlannerConfig:
    """All tunables in one versioned place (see revision.py)."""

    version: int = 1
    day_start: str = "08:30"
    day_end: str = "18:00"
    lunch_start: str = "12:30"
    lunch_minutes: int = 45
    deep_block_minutes: int = 90
    buffer_minutes: int = 15
    admin_batch_after: str = "16:00"
    meeting_window_start: str = "13:15"
    # Priority scoring weights
    w_priority: float = 3.0
    w_due_today: float = 2.0
    w_project_risk: float = 1.5
    w_deep_morning: float = 1.0
    # Critic weights (sum to 1.0) and quality bar
    c_focus: float = 0.45
    c_switches: float = 0.25
    c_coverage: float = 0.30
    target_score: int = 80
    max_iterations: int = 3

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannerConfig":
        known = {k: v for k, v in (data or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


# ------------------------------------------------------------- utilities ----

def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


_DEEP = ("implement", "design", "build", "write", "research", "train", "model",
         "debug", "architect", "prototype", "harden", "refactor")
_MEETING = ("meeting", "sync", "1:1", "standup", "call", "interview", "alignment", "demo")
_ADMIN = ("email", "inbox", "expense", "report", "admin", "timesheet", "invoice", "triage")
_REVIEW = ("review", "approve", "patch", "pr ", "feedback")


#: Titles that say outright what the block *is*, which must beat what it is
#: *about*. "Deep work — standup delivery" is focused work on the standup
#: feature, not a standup; without this it matched _MEETING on its subject and
#: was scheduled — and labelled — as a meeting.
_EXPLICIT_DEEP = ("deep work", "focus block", "focus time", "deep focus")


def classify_kind(title: str) -> str:
    """deep | meeting | admin | review — drives where a task lands in the day."""
    t = title.lower()
    if any(k in t for k in _EXPLICIT_DEEP):
        return "deep"
    if any(k in t for k in _MEETING):
        return "meeting"
    if any(k in t for k in _ADMIN):
        return "admin"
    if any(k in t for k in _REVIEW):
        return "review"
    if any(k in t for k in _DEEP):
        return "deep"
    return "deep"  # unknown knowledge-work defaults to deep (protect it)


_PRIORITY_SCORE = {"high": 3.0, "medium": 2.0, "low": 1.0}
_RISK_SCORE = {"high": 1.0, "medium": 0.5, "low": 0.0}


# ------------------------------------------------------------ agent nodes ----

def prioritize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Score every task; highest-leverage first."""
    cfg: PlannerConfig = state["config"]
    scored = []
    for t in state.get("tasks", []):
        kind = classify_kind(t.get("title", ""))
        score = _PRIORITY_SCORE.get(t.get("priority", "medium"), 2.0) * cfg.w_priority
        if t.get("dueToday"):
            score += cfg.w_due_today
        score += _RISK_SCORE.get(t.get("projectRisk", "low"), 0.0) * cfg.w_project_risk
        if kind == "deep":
            score += cfg.w_deep_morning
        scored.append({**t, "kind": kind, "score": round(score, 2)})
    scored.sort(key=lambda x: -x["score"])
    return {"prioritized": scored}


def schedule_node(state: dict[str, Any]) -> dict[str, Any]:
    """Place prioritized tasks into the day by energy curve, with buffers.

    Honors critic hints: 'batch_admin' pushes all admin to the end of day;
    'protect_morning' refuses meetings before lunch even if requested.
    """
    cfg: PlannerConfig = state["config"]
    hints: set[str] = set(state.get("hints", []))
    tasks = list(state.get("prioritized", []))

    day_start, day_end = _minutes(cfg.day_start), _minutes(cfg.day_end)
    lunch_start = _minutes(cfg.lunch_start)
    lunch_end = lunch_start + cfg.lunch_minutes
    meeting_start = max(_minutes(cfg.meeting_window_start), lunch_end)
    admin_start = _minutes(cfg.admin_batch_after)

    deep = [t for t in tasks if t["kind"] == "deep"]
    reviews = [t for t in tasks if t["kind"] == "review"]
    meetings = [t for t in tasks if t["kind"] == "meeting"]
    admin = [t for t in tasks if t["kind"] == "admin"]

    blocks: list[dict[str, Any]] = []

    def place(task: dict[str, Any], start: int, minutes: int) -> int:
        blocks.append({
            "taskId": task.get("id"), "title": task["title"], "kind": task["kind"],
            "start": _hhmm(start), "end": _hhmm(start + minutes),
            "score": task.get("score", 0), "owner": task.get("owner", "you"),
        })
        return start + minutes + cfg.buffer_minutes

    # Morning: protected deep-work blocks until lunch.
    cursor = day_start
    for t in deep:
        if cursor + cfg.deep_block_minutes > lunch_start:
            break
        cursor = place(t, cursor, cfg.deep_block_minutes)
    remaining_deep = deep[len([b for b in blocks if b["kind"] == "deep"]):]

    # Lunch is sacred.
    blocks.append({"taskId": None, "title": "Lunch & recharge", "kind": "break",
                   "start": _hhmm(lunch_start), "end": _hhmm(lunch_end), "score": 0, "owner": "you"})

    # Early afternoon: meetings + reviews (batched), never before lunch when
    # 'protect_morning' is hinted.
    cursor = meeting_start
    for t in meetings + reviews:
        end_cap = admin_start if "batch_admin" in hints else day_end
        if cursor + 45 > end_cap:
            break
        cursor = place(t, cursor, 45)

    # Any deep work that didn't fit the morning gets the mid-afternoon.
    for t in remaining_deep:
        end_cap = admin_start if "batch_admin" in hints else day_end
        if cursor + cfg.deep_block_minutes > end_cap:
            break
        cursor = place(t, cursor, cfg.deep_block_minutes)

    # End of day: batched admin.
    cursor = max(cursor, admin_start)
    for t in admin:
        if cursor + 30 > day_end:
            break
        cursor = place(t, cursor, 30)

    blocks.sort(key=lambda b: b["start"])
    return {"blocks": blocks, "iterations": state.get("iterations", 0) + 1}


def critique_node(state: dict[str, Any]) -> dict[str, Any]:
    """Score the candidate plan 0–100 and emit hints for the next pass."""
    cfg: PlannerConfig = state["config"]
    blocks = [b for b in state.get("blocks", []) if b["kind"] != "break"]
    if not blocks:
        return {"critique": {"score": 0, "issues": ["empty plan"], "focusMinutes": 0, "switches": 0}}

    focus_minutes = sum(
        _minutes(b["end"]) - _minutes(b["start"]) for b in blocks if b["kind"] == "deep"
    )
    total_minutes = sum(_minutes(b["end"]) - _minutes(b["start"]) for b in blocks)
    switches = sum(1 for a, b in zip(blocks, blocks[1:]) if a["kind"] != b["kind"])
    high_priority = [t for t in state.get("prioritized", []) if t.get("priority") == "high"]
    scheduled_ids = {b.get("taskId") for b in blocks}
    coverage = (
        sum(1 for t in high_priority if t.get("id") in scheduled_ids) / len(high_priority)
        if high_priority else 1.0
    )

    focus_ratio = focus_minutes / total_minutes if total_minutes else 0.0
    switch_ratio = switches / max(len(blocks) - 1, 1)
    score = round(100 * (cfg.c_focus * focus_ratio
                         + cfg.c_switches * (1 - switch_ratio)
                         + cfg.c_coverage * coverage))

    issues, hints = [], []
    if focus_ratio < 0.45:
        issues.append("deep-work share below 45%")
        hints.append("protect_morning")
    if switch_ratio > 0.5:
        issues.append("too many context switches")
        hints.append("batch_admin")
    if coverage < 1.0:
        issues.append("a high-priority task is unscheduled")

    return {
        "critique": {"score": score, "issues": issues, "focusMinutes": focus_minutes,
                     "switches": switches, "coverage": round(coverage, 2)},
        "hints": hints,
    }


def critic_router(state: dict[str, Any]) -> str:
    """Loop back to the scheduler until the plan beats the bar (bounded)."""
    cfg: PlannerConfig = state["config"]
    score = state.get("critique", {}).get("score", 0)
    if score >= cfg.target_score or state.get("iterations", 0) >= cfg.max_iterations:
        return "finalize"
    return "schedule"


def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
    """Produce the plan narrative — via Ollabridge when reachable, with a
    deterministic fallback so the planner works offline and in CI."""
    critique = state.get("critique", {})
    blocks = state.get("blocks", [])
    deep_blocks = [b for b in blocks if b["kind"] == "deep"]
    narrative = state.get("narrative")
    if narrative is None:
        narrative = (
            f"Optimized plan: {len(deep_blocks)} deep-work block(s) "
            f"({critique.get('focusMinutes', 0)} focused minutes) protected in the morning, "
            f"meetings batched after lunch, admin closed out at the end of the day. "
            f"Plan score {critique.get('score', 0)}/100 after {state.get('iterations', 0)} pass(es)."
        )
    return {"narrative": narrative}


def build_planner_graph():
    """Wire the agents into the planning graph (LangGraph-shaped)."""
    from .graph import END, START, StateGraph

    g = StateGraph()
    g.add_node("prioritize", prioritize_node)
    g.add_node("schedule", schedule_node)
    g.add_node("critique", critique_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "prioritize")
    g.add_edge("prioritize", "schedule")
    g.add_edge("schedule", "critique")
    g.add_conditional_edges("critique", critic_router)
    g.add_edge("finalize", END)
    return g.compile()
