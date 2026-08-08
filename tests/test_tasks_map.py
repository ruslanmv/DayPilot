"""Turning API tasks into the shell's task shape.

Calendar, Tasks and Focus Mode all read one list of tasks. The API returns open
strings where the UI expects closed unions, and `day` is a weekday name that
older rows stored as an ISO date — so a wrong guess here shows a task under the
wrong day, with no owner, or drops it from the week entirely. The rules live in
`packages/ui-bridge/src/tasksMap.ts` and are run here by node.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "packages" / "ui-bridge" / "src" / "tasksMap.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def run(expr: str):
    script = (
        f"import {{ toDayPilotTask, toWeekday, focusCandidate }} from {json.dumps(str(MAP))}\n"
        f"console.log(JSON.stringify({expr}))\n"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def task(**kw):
    base = {"id": "t1", "title": "Deep work", "owner": "you", "priority": "high",
            "status": "active", "day": "Monday", "start": "09:00", "end": "11:30"}
    base.update(kw)
    return base


# --- day ---------------------------------------------------------------------

def test_a_weekday_name_survives_the_round_trip():
    assert run('toWeekday("Wednesday")') == "Wednesday"
    assert run('toWeekday("friday")') == "Friday"


def test_an_iso_date_is_placed_on_its_real_weekday():
    # Older rows stored a date here. Dropping such a task out of the week would
    # be worse than translating it.
    assert run('toWeekday("2026-08-05")') == "Wednesday"


def test_a_task_with_no_day_lands_on_today_rather_than_disappearing():
    assert run('toWeekday(null, new Date(2026, 7, 6))') == "Thursday"
    assert run('toWeekday("", new Date(2026, 7, 9))') == "Sunday"


def test_a_sunday_maps_to_the_end_of_the_week_not_the_start():
    # JS weeks start on Sunday and the shell's do not; getting this wrong moves
    # every task by a day.
    assert run('toWeekday(null, new Date(2026, 7, 9))') == "Sunday"
    assert run('toWeekday(null, new Date(2026, 7, 10))') == "Monday"


# --- field mapping -----------------------------------------------------------

def test_a_server_task_becomes_a_shell_task():
    t = run(f"toDayPilotTask({json.dumps(task(context='ctx', executor='GitPilot'))})")
    assert t["id"] == "t1"
    assert t["title"] == "Deep work"
    assert t["start"] == "09:00"
    assert t["end"] == "11:30"
    assert t["owner"] == "you"
    assert t["status"] == "active"
    assert t["context"] == "ctx"
    assert t["executor"] == "GitPilot"


def test_open_string_fields_are_narrowed_and_unknown_values_fall_back():
    t = run(f"toDayPilotTask({json.dumps(task(owner='ROBOT', priority='urgent', status='???'))})")
    assert t["owner"] == "you"
    assert t["priority"] == "medium"
    assert t["status"] == "scheduled"


def test_case_differences_do_not_lose_a_valid_value():
    t = run(f"toDayPilotTask({json.dumps(task(owner='AI', priority='Critical', status='Blocked'))})")
    assert t["owner"] == "ai"
    assert t["priority"] == "critical"
    assert t["status"] == "blocked"


def test_a_task_with_no_times_still_maps():
    t = run(f"toDayPilotTask({json.dumps(task(start=None, end=None))})")
    assert t["start"] == ""
    assert t["end"] == ""


# --- what "start focus" opens ------------------------------------------------

def test_focus_opens_the_block_that_is_already_running():
    rows = [task(id="later", status="scheduled", start="16:00"),
            task(id="now", status="running", start="09:00")]
    mapped = f"{json.dumps(rows)}.map(toDayPilotTask)"
    assert run(f"focusCandidate({mapped})")["id"] == "now"


def test_otherwise_focus_opens_the_earliest_thing_still_ahead():
    rows = [task(id="afternoon", status="scheduled", start="16:00"),
            task(id="morning", status="scheduled", start="09:00")]
    mapped = f"{json.dumps(rows)}.map(toDayPilotTask)"
    assert run(f"focusCandidate({mapped})")["id"] == "morning"


def test_focus_never_opens_something_already_finished():
    rows = [task(id="done", status="done", start="08:00"),
            task(id="open", status="scheduled", start="15:00")]
    mapped = f"{json.dumps(rows)}.map(toDayPilotTask)"
    assert run(f"focusCandidate({mapped})")["id"] == "open"


def test_an_unscheduled_task_is_better_than_opening_nothing():
    rows = [task(id="whenever", status="scheduled", start=None)]
    mapped = f"{json.dumps(rows)}.map(toDayPilotTask)"
    assert run(f"focusCandidate({mapped})")["id"] == "whenever"


def test_an_empty_day_opens_nothing_rather_than_crashing():
    assert run("focusCandidate([]) ?? null") is None
