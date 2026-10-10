"""What the Echo Show display says, and when it asks again.

The Echo dashboard (`/echo`) hangs on a wall and is read from across a room, so
its rules have to be right without anyone checking them in a browser: how a
failed request is explained, how quickly it retries, which events count as
today, how tasks are grouped so a tile and its list agree. They live in
`packages/ui-bridge/src/echo/echoModel.ts` and are run here by node.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "packages" / "ui-bridge" / "src" / "echo" / "echoModel.ts"
NAMES = [
    "classifyFailure", "failureText", "isRetryable", "retryDelay", "nextRefreshIn", "ECHO_TIMING",
    "parseEchoHash", "greeting", "updatedLabel", "eventsOnDay", "upcomingDays", "parseWhen",
    "groupTasks", "weekdayName", "rankProjects", "needsAttention", "splitRuns", "sameData",
    "msToNextMinute",
]

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def run(expr: str):
    script = (
        f"import {{ {', '.join(NAMES)} }} from {json.dumps(str(MODEL))}\n"
        f"console.log(JSON.stringify({expr}))\n"
    )
    proc = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node failed:\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# --- failures ------------------------------------------------------------------

@pytest.mark.parametrize("result,online,kind", [
    ({"error": "Failed to fetch"}, True, "unreachable"),
    ({"error": "Failed to fetch"}, False, "offline"),
    ({"error": "not_authenticated", "status": 401}, True, "auth"),
    ({"error": "Role 'reviewer' lacks required role 'operator'.", "status": 403}, True, "forbidden"),
    ({"error": "No plan for that date", "status": 404}, True, "not_found"),
    ({"error": "Approval already approved", "status": 409}, True, "conflict"),
    ({"error": "gateway_html_response", "status": 200}, True, "misrouted"),
    ({"error": "HTTP 502", "status": 502}, True, "server"),
    ({"error": "HTTP 422", "status": 422}, True, "error"),
])
def test_a_failed_request_is_classified_once(result, online, kind):
    assert run(f"classifyFailure({json.dumps(result)}, {{ online: {json.dumps(online)} }}).kind") == kind


def test_a_request_abandoned_by_the_timer_is_a_timeout_not_an_outage():
    assert run('classifyFailure({ error: "aborted" }, { online: true, timedOut: true }).kind') == "timeout"


def test_the_servers_own_reason_is_kept_for_permission_and_conflict_answers():
    # A role that may not decide must read the server's explanation, not a guess.
    detail = "Deciding a 'coding_run' approval requires role 'operator'."
    assert run(f'failureText({{ kind: "forbidden", status: 403, detail: {json.dumps(detail)} }})') == detail
    assert run('failureText({ kind: "forbidden", status: 403, detail: "HTTP 403" })') == "Your role does not allow this."
    assert run('failureText({ kind: "conflict", status: 409, detail: "Approval already approved" })') == "Approval already approved"


def test_only_failures_that_can_fix_themselves_are_retried_on_a_timer():
    retry = run('["offline","unreachable","timeout","server","misrouted","auth","forbidden","not_found","conflict"]'
                '.map((kind) => isRetryable({ kind, detail: "" }))')
    assert retry == [True, True, True, True, True, False, False, False, False]


# --- timing --------------------------------------------------------------------

def test_retries_back_off_and_never_loop_tightly():
    assert run("[0, 1, 2, 3, 4, 5, 6, 20].map((n) => retryDelay(n))") == [
        15_000, 15_000, 30_000, 60_000, 120_000, 240_000, 300_000, 300_000,
    ]


def test_the_live_tier_slows_down_when_nobody_has_touched_the_screen():
    assert run('nextRefreshIn("live", 0, false)') == 60_000
    assert run('nextRefreshIn("live", 0, true)') == 300_000
    assert run('nextRefreshIn("slow", 0, false)') == 300_000
    assert run('nextRefreshIn("live", 2, false)') == 30_000


def test_every_request_has_a_deadline():
    assert run("ECHO_TIMING.timeoutMs") == 15_000


def test_the_clock_wakes_just_after_the_minute_turns():
    assert run("msToNextMinute(new Date(2026, 9, 10, 10, 40, 59, 500))") == 550
    assert run("msToNextMinute(new Date(2026, 9, 10, 10, 40, 0, 0))") == 60_050


# --- navigation and copy ---------------------------------------------------------

@pytest.mark.parametrize("hash_,section", [
    ("#/approvals", "approvals"), ("#approvals", "approvals"), ("#/tasks?x=1", "tasks"),
    ("", "today"), ("#/settings", "today"), ("#/../../etc", "today"),
])
def test_an_unknown_address_opens_today_not_a_blank_page(hash_, section):
    assert run(f"parseEchoHash({json.dumps(hash_)})") == section


def test_the_greeting_uses_the_first_name_and_the_local_hour():
    assert run('greeting(new Date(2026, 9, 10, 10, 40), "Alex Morgan")') == "Good morning, Alex"
    assert run('greeting(new Date(2026, 9, 10, 13, 0), null)') == "Good afternoon"
    assert run('greeting(new Date(2026, 9, 10, 23, 0), "  ")') == "Good evening"
    assert run('greeting(new Date(2026, 9, 10, 3, 0), "Sam")') == "Good evening, Sam"


def test_the_age_of_what_is_shown_is_always_stated():
    now = "Date.UTC(2026, 9, 10, 8, 40)"
    assert run(f"updatedLabel(null, {now})") == "Not loaded yet"
    assert run(f"updatedLabel({now} - 20000, {now})") == "Updated just now"
    assert run(f"updatedLabel({now} - 4 * 60000, {now})") == "Updated 4 min ago"


# --- calendar ------------------------------------------------------------------

EVENTS = [
    {"id": "a", "title": "Standup", "startAt": "2026-10-10T09:00:00", "endAt": "2026-10-10T09:15:00", "status": "confirmed"},
    {"id": "b", "title": "Sync", "startAt": "2026-10-10T11:00:00", "endAt": "2026-10-10T11:30:00", "status": "confirmed"},
    {"id": "c", "title": "Vendor demo", "startAt": "2026-10-10T16:00:00", "endAt": "2026-10-10T17:00:00", "status": "cancelled"},
    {"id": "d", "title": "Offsite", "startAt": "2026-10-09T09:00:00", "endAt": "2026-10-11T17:00:00", "status": "confirmed"},
    {"id": "e", "title": "Brunch", "startAt": "2026-10-11T11:00:00", "endAt": "2026-10-11T13:00:00", "status": "tentative"},
    {"id": "f", "title": "No time", "startAt": None, "endAt": None},
    {"id": "g", "title": "Holiday", "startAt": "2026-10-12", "endAt": None},
]
NOW = "new Date(2026, 9, 10, 10, 40)"


def test_today_leaves_out_cancelled_and_untimed_events_and_keeps_multi_day_ones():
    titles = run(f"eventsOnDay({json.dumps(EVENTS)}, {NOW}, {NOW}).map((e) => e.title)")
    assert titles == ["Offsite", "Standup", "Sync"]


def test_today_marks_past_and_overlapping_events():
    rows = run(f"eventsOnDay({json.dumps(EVENTS)}, {NOW}, {NOW}, [{{ a: 'a', b: 'b' }}])"
               ".map((e) => [e.id, e.isPast, e.isNow, e.conflict])")
    assert rows == [["d", False, True, False], ["a", True, False, True], ["b", False, False, True]]


def test_the_next_days_show_only_days_that_have_events():
    days = run(f"upcomingDays({json.dumps(EVENTS)}, {NOW}).map((d) => [d.day.getDate(), d.events.map((e) => e.title)])")
    assert days == [[11, ["Offsite", "Brunch"]], [12, ["Holiday"]]]
    assert run(f"upcomingDays({json.dumps(EVENTS)}, {NOW})[0].events[1].tentative") is True


def test_a_date_without_a_time_is_an_all_day_event_on_that_local_day():
    assert run('[parseWhen("2026-10-12").getDate(), parseWhen("2026-10-12").getHours()]') == [12, 0]
    assert run('parseWhen("not a date")') is None


# --- tasks -----------------------------------------------------------------------

def task(i, status, day="Saturday", start="", priority="medium"):
    return {"id": f"t{i}", "title": f"T{i}", "day": day, "start": start, "end": "", "owner": "you",
            "executor": "", "priority": priority, "status": status, "context": ""}


def test_each_open_task_lands_in_exactly_one_group_and_done_tasks_in_none():
    tasks = [task(1, "blocked"), task(2, "needs_approval"), task(3, "running"), task(4, "active"),
             task(5, "scheduled"), task(6, "scheduled", day="Monday"), task(7, "done")]
    g = run(f"groupTasks({json.dumps(tasks)}, {NOW})")
    ids = lambda key: [t["id"] for t in g[key]]  # noqa: E731
    assert g["open"] == 6
    assert ids("blocked") == ["t1"]
    assert ids("needsApproval") == ["t2"]
    assert ids("inProgress") == ["t3", "t4"]
    assert ids("today") == ["t5"]
    assert ids("later") == ["t6"]


def test_groups_read_in_time_order_then_by_priority():
    tasks = [task(1, "scheduled", start="15:00"), task(2, "scheduled"), task(3, "scheduled", start="09:00"),
             task(4, "scheduled", start="09:00", priority="critical")]
    assert run(f"groupTasks({json.dumps(tasks)}, {NOW}).today.map((t) => t.id)") == ["t4", "t3", "t1", "t2"]


def test_the_week_starts_on_monday_like_the_rest_of_daypilot():
    assert run("[weekdayName(new Date(2026, 9, 11)), weekdayName(new Date(2026, 9, 12))]") == ["Sunday", "Monday"]


# --- projects and agents ---------------------------------------------------------

def test_projects_riskiest_first_and_attention_matches_the_server_count():
    projects = [{"id": "1", "name": "B", "risk": "low"}, {"id": "2", "name": "A", "risk": "high"},
                {"id": "3", "name": "C", "risk": "medium"}, {"id": "4", "name": "A2", "risk": "low"}]
    assert run(f"rankProjects({json.dumps(projects)}).map((p) => p.id)") == ["2", "3", "4", "1"]
    # /v1/today counts `risk != "low"` as needing attention; so does the list.
    assert run(f"{json.dumps(projects)}.filter(needsAttention).length") == 2


def test_running_means_the_same_as_the_servers_ai_running_count():
    runs = [{"id": "1", "name": "a", "state": "running", "status": "Running"},
            {"id": "2", "name": "b", "state": "failed", "status": "Blocked"},
            {"id": "3", "name": "c", "state": "succeeded", "status": "Needs Approval"},
            {"id": "4", "name": "d", "state": "succeeded", "status": "Done"},
            {"id": "5", "name": "e", "state": "queued", "status": "Running"}]
    split = run(f"splitRuns({json.dumps(runs)})")
    assert [r["id"] for r in split["running"]] == ["1"]
    assert [r["id"] for r in split["attention"]] == ["2", "3"]
    assert [r["id"] for r in split["recent"]] == ["4", "5"]


def test_an_unchanged_refresh_is_recognised_so_nothing_re_renders():
    assert run('sameData({ a: [1, 2], b: null }, { a: [1, 2], b: null })') is True
    assert run('sameData({ a: [1, 2] }, { a: [2, 1] })') is False
