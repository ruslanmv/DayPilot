"""Home renders the real day.

Home's Next priority / Today's plan / Continue-from-yesterday cards are built
from three API responses by pure functions in
`packages/ui-bridge/src/home/homeDay.ts`. The rules there are product
decisions, not plumbing — which projects have genuinely carried something over,
what a plan block is called, what a card says when a task has no scheduled
time — so they are tested against the shipped code rather than a Python
re-implementation of it.

The module is executed by node with type stripping (its imports are
type-only), which keeps the test honest: it fails if the real file changes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOME_DAY = ROOT / "packages" / "ui-bridge" / "src" / "home" / "homeDay.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def run(expr: str, *, imports: str = "toAgenda, toContinue, toPriority, blockTag, timeRange, continuityStatus, planDateKey"):
    """Evaluate an expression against the real module and return the JSON result."""
    script = (
        f"import {{ {imports} }} from {json.dumps(str(HOME_DAY))}\n"
        f"console.log(JSON.stringify({expr}))\n"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# --- Today's plan ------------------------------------------------------------

def test_blocks_are_shown_in_plan_order_not_response_order():
    blocks = [
        {"id": "c", "title": "Wrap up", "start": "17:00", "orderIndex": 2},
        {"id": "a", "title": "Deep work", "start": "09:00", "orderIndex": 0},
        {"id": "b", "title": "Standup", "start": "11:00", "orderIndex": 1},
    ]
    titles = [row["title"] for row in run(f"toAgenda({json.dumps(blocks)})")]
    assert titles == ["Deep work", "Standup", "Wrap up"]


def test_a_block_with_a_range_shows_it_and_a_single_time_does_not_repeat_itself():
    blocks = [
        {"id": "a", "title": "Deep work", "start": "09:00", "end": "11:30", "orderIndex": 0},
        {"id": "b", "title": "Standup", "start": "11:45", "orderIndex": 1},
    ]
    rows = run(f"toAgenda({json.dumps(blocks)})")
    assert rows[0]["end"] == "09:00 – 11:30"
    # The start column already says 11:45; repeating it in the trailing slot
    # would be noise, so the field is left off entirely.
    assert "end" not in rows[1] or rows[1]["end"] is None


def test_a_block_with_no_time_still_renders():
    rows = run('toAgenda([{ id: "a", title: "Unscheduled", orderIndex: 0 }])')
    assert rows[0]["time"] == "—"
    assert rows[0]["title"] == "Unscheduled"


def test_the_tag_names_who_or_what_the_block_belongs_to():
    assert run('blockTag({ id: "a", title: "t", owner: "ai", source: "gitpilot" })') == "AI"
    assert run('blockTag({ id: "a", title: "t", source: "gitpilot" })') == "GitPilot"
    assert run('blockTag({ id: "a", title: "t", source: "claude_code" })') == "Claude Code"
    assert run('blockTag({ id: "a", title: "t", source: "" })') == "Focus"
    # Something the label table has never seen is shown as written, tidied —
    # better than mislabelling it "Focus".
    assert run('blockTag({ id: "a", title: "t", source: "design_review" })') == "Design Review"


def test_a_time_range_needs_both_ends():
    assert run('timeRange("09:00", "11:00")') == "09:00 – 11:00"
    assert run('timeRange("09:00", null)') == "09:00"
    assert run('timeRange(null, null)') == ""


# --- Next priority -----------------------------------------------------------

def test_the_priority_takes_its_time_from_the_matching_plan_block():
    now = {"id": "t1", "title": "Ship the standup worker", "projectId": "p1", "start": "08:00"}
    blocks = [{"id": "b1", "taskId": "t1", "title": "Ship it", "start": "09:00",
               "end": "11:30", "orderIndex": 0}]
    row = run(f"toPriority({json.dumps(now)}, {json.dumps(blocks)}, {{ p1: 'DayPilot' }})")
    # The plan is the schedule of record; the task's own time is the fallback.
    assert row["time"] == "09:00 – 11:30"
    assert row["project"] == "DayPilot"


def test_a_priority_with_no_block_and_no_project_still_has_a_title():
    now = {"id": "t1", "title": "Unscheduled but urgent"}
    row = run(f"toPriority({json.dumps(now)}, [], {{}})")
    assert row["title"] == "Unscheduled but urgent"
    assert row["time"] == ""
    assert row["project"] == ""


def test_no_active_task_means_no_priority_card():
    assert run("toPriority(null, [], {})") is None


# --- Continue from yesterday -------------------------------------------------

def test_only_projects_that_actually_carried_something_over_are_shown():
    items = [
        {"projectId": "p1", "name": "Fresh", "nextAction": "Review project status"},
        {"projectId": "p2", "name": "Real", "yesterday": ["Shipped the collector"]},
    ]
    rows = run(f"toContinue({json.dumps(items)})")
    # A project with no history would otherwise appear as a generic
    # "Next: Review project status" line — filler this product exists to avoid.
    assert [r["name"] for r in rows] == ["Real"]


def test_a_blocker_outranks_yesterdays_progress_in_the_status_line():
    item = {"projectId": "p", "name": "N", "yesterday": ["Shipped the collector"],
            "blockers": ["Waiting on the Slack scope"], "aiActivity": "Indexing"}
    assert run(f"continuityStatus({json.dumps(item)})") == "Blocked: Waiting on the Slack scope"


def test_the_status_line_falls_back_through_yesterday_then_ai_then_a_neutral_phrase():
    base = {"projectId": "p", "name": "N"}
    assert run(f"continuityStatus({json.dumps({**base, 'yesterday': ['Did a thing']})})") == "Did a thing"
    assert run(f"continuityStatus({json.dumps({**base, 'aiActivity': 'Indexing docs'})})") == "Indexing docs"
    assert run(f"continuityStatus({json.dumps(base)})") == "In progress"


def test_progress_is_clamped_so_a_bad_number_cannot_overflow_the_bar():
    items = [
        {"projectId": "a", "name": "Over", "progress": 140, "yesterday": ["x"]},
        {"projectId": "b", "name": "Under", "progress": -20, "yesterday": ["x"]},
    ]
    rows = run(f"toContinue({json.dumps(items)})")
    assert [r["progress"] for r in rows] == [100, 0]


def test_the_card_shows_at_most_three_projects():
    items = [{"projectId": f"p{i}", "name": f"P{i}", "yesterday": ["x"]} for i in range(8)]
    assert len(run(f"toContinue({json.dumps(items)})")) == 3


def test_risk_drives_the_accent_and_a_blocked_project_is_marked():
    items = [{"projectId": "p", "name": "N", "risk": "high", "blockers": ["b"]}]
    row = run(f"toContinue({json.dumps(items)})")[0]
    assert row["accent"] == "purple"
    assert row["icon"] == "⚠"


# --- Plan lookup -------------------------------------------------------------

def test_the_plan_is_looked_up_by_the_local_date_not_utc():
    # 00:30 local on the 9th is still the 8th in UTC. Asking for the UTC date
    # would show yesterday's plan to anyone east of Greenwich after midnight.
    key = run("planDateKey(new Date(2026, 7, 9, 0, 30))")
    assert key == "2026-08-09"
