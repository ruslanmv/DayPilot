"""Seed a throwaway workspace for the Echo display E2E (tests/ui/echo-e2e.mjs).

Everything a user or an integration would create goes through the gateway's real API
(owner bootstrap, projects, tasks, the day plan, a calendar draft that raises an
approval). Rows that only a provider sync or an agent run would write — confirmed
calendar events, approvals raised by agents, agent runs — go in through the ORM against
the same database. The day is Saturday 2026-10-10; the E2E pins the browser clock to
10:40 Europe/Berlin.

    DATABASE_URL=sqlite:///… python tests/ui/echo_seed.py http://127.0.0.1:8891
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8891"
DAY = "Saturday"
PLAN_DATE = "2026-10-10"

c = httpx.Client(base_url=BASE, timeout=20)
r = c.post("/v1/auth/bootstrap", json={"email": "alex@example.com", "password": "correct-horse-42",
                                        "displayName": "Alex Morgan", "workspaceName": "Morgan Studio"})
r.raise_for_status()

projects = {}
for name, risk, progress, nxt in [
    ("Client Alpha portal", "high", 62, "Confirm the release scope with Client Alpha"),
    ("DayPilot Echo display", "medium", 48, "Review the Echo layout on the device"),
    ("Payments API v2", "low", 81, "Approve the staging deploy"),
    ("Hiring: senior designer", "low", 35, "Shortlist portfolios"),
    ("Q4 board deck", "medium", 20, "Draft the revenue section"),
]:
    r = c.post("/v1/projects", json={"name": name, "risk": risk, "goal": name})
    r.raise_for_status()
    p = r.json()
    c.patch(f"/v1/projects/{p['id']}", json={"progress": progress, "nextHumanAction": nxt}).raise_for_status()
    projects[name] = p["id"]

def task(title, status, start=None, end=None, owner="you", priority="medium", day=DAY, project=None, context=None, executor=""):
    r = c.post("/v1/tasks", json={"title": title, "status": status, "start": start, "end": end, "owner": owner,
                                  "priority": priority, "day": day, "projectId": projects.get(project),
                                  "context": context, "executor": executor})
    r.raise_for_status()

task("Finish Client Alpha release notes", "active", "10:00", "11:30", priority="high", project="Client Alpha portal",
     context="Notes are drafted; add the migration steps and send for review.")
task("Review Echo layout on the device", "scheduled", "12:00", "12:45", project="DayPilot Echo display")
task("Lunch with Sam", "scheduled", "13:00", "14:00", priority="low")
task("Payments API staging deploy", "needs_approval", "14:30", "15:00", owner="ai", executor="GitPilot", priority="high", project="Payments API v2")
task("Draft Q4 revenue section", "scheduled", "15:30", "17:00", project="Q4 board deck")
task("Patch auth token refresh", "running", "09:30", "12:00", owner="ai", executor="GitPilot", priority="high", project="Client Alpha portal")
task("Summarize designer portfolios", "running", None, None, owner="ai", executor="Document Assistant", project="Hiring: senior designer")
task("Client Alpha SSO certificate", "blocked", owner="team", priority="critical", project="Client Alpha portal")
task("Board deck numbers from finance", "blocked", priority="high", project="Q4 board deck")
task("Morning plan review", "done", "08:30", "08:45")
task("Prepare Monday standup", "scheduled", "09:00", "09:30", day="Monday")
task("1:1 with Priya", "scheduled", "11:00", "11:30", day="Tuesday")
task("Renew domain certificates", "scheduled", day="Wednesday", priority="low")

r = c.post(f"/v1/plans/{PLAN_DATE}/draft")
r.raise_for_status()
r = c.post("/v1/calendar/events/draft", json={"title": "Design review: Echo display", "startAt": "2026-10-12T16:00:00",
                                                "endAt": "2026-10-12T16:30:00"})
r.raise_for_status()

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "knowledge-service"))
from daypilot_knowledge.db import AgentRun, Approval, CalendarEvent, Project, create_engine_from_settings, session_scope  # noqa: E402

engine = create_engine_from_settings()
now = datetime(2026, 10, 10, 8, 40, tzinfo=timezone.utc)  # 10:40 in Berlin
with session_scope(engine) as s:
    for title, start, end, status in [
        ("Client Alpha weekly sync", "2026-10-10T11:00:00", "2026-10-10T11:30:00", "confirmed"),
        ("Release check-in", "2026-10-10T11:15:00", "2026-10-10T11:45:00", "confirmed"),
        ("Lunch with Sam", "2026-10-10T13:00:00", "2026-10-10T14:00:00", "confirmed"),
        ("Yoga", "2026-10-10T18:30:00", "2026-10-10T19:30:00", "tentative"),
        ("Breakfast meetup", "2026-10-10T08:00:00", "2026-10-10T09:00:00", "confirmed"),
        ("Cancelled: vendor demo", "2026-10-10T16:00:00", "2026-10-10T17:00:00", "cancelled"),
        ("Family brunch", "2026-10-11T11:00:00", "2026-10-11T13:00:00", "confirmed"),
        ("Monday standup", "2026-10-12T09:00:00", "2026-10-12T09:15:00", "confirmed"),
        ("Payments API launch review", "2026-10-12T14:00:00", "2026-10-12T15:00:00", "confirmed"),
        ("1:1 with Priya", "2026-10-13T11:00:00", "2026-10-13T11:30:00", "confirmed"),
        ("Board prep", "2026-10-15T10:00:00", "2026-10-15T12:00:00", "confirmed"),
        ("Last quarter's offsite", "2026-07-01T10:00:00", "2026-07-01T17:00:00", "confirmed"),
    ]:
        s.add(CalendarEvent(workspace_id="default", title=title, start_at=datetime.fromisoformat(start),
                            end_at=datetime.fromisoformat(end), status=status, source="google"))
    for action, summary, risk, rtype, status, mins in [
        ("Send release notes to Client Alpha", "Email to 3 recipients at Client Alpha with the 2.4 release notes attached.", "medium", "email", "pending", 12),
        ("Deploy Payments API v2 to staging", "GitPilot prepared build 2.0.0-rc3; 214 tests passed. Deploys to the staging cluster.", "high", "deployment", "pending", 34),
        ("Share Q4 board deck folder with finance", "Gives finance@ edit access to 'Q4 board deck'.", "low", "document", "pending", 55),
        ("Archive 42 newsletters", "Moves newsletters older than 30 days to Archive.", "low", "email", "approved", 180),
        ("Post incident summary to #eng", "Slack message to #eng summarising Thursday's outage.", "medium", "slack", "rejected", 240),
    ]:
        s.add(Approval(workspace_id="default", action=action, summary=summary, risk=risk, resource_type=rtype,
                       status=status, created_at=now - timedelta(minutes=mins),
                       decided_at=(now - timedelta(minutes=mins - 20)) if status != "pending" else None))
    for name, kind, work, state, status, err, mins in [
        ("GitPilot", "coding", "Patching auth token refresh in Client Alpha portal", "running", "Running", None, 3),
        ("Document Assistant", "documents", "Summarizing 18 designer portfolios", "running", "Running", None, 6),
        ("Email Sentinel", "email", "Drafted reply to Client Alpha — waiting for approval", "succeeded", "Needs Approval", None, 15),
        ("Scheduler", "planning", "Rebalanced next week's focus blocks", "succeeded", "Done", None, 75),
        ("Project Analyst", "analysis", "Risk scan of Q4 board deck", "failed", "Blocked", "Finance spreadsheet is not shared with DayPilot.", 40),
    ]:
        s.add(AgentRun(workspace_id="default", name=name, agent_kind=kind, current_work=work, state=state,
                       display_status=status, last_error=err, created_at=now - timedelta(minutes=mins + 30),
                       updated_at=now - timedelta(minutes=mins)))
    for p in s.query(Project).all():
        p.ai_activity = {
            "Client Alpha portal": "GitPilot is patching the auth token refresh.",
            "Hiring: senior designer": "Summarizing 18 portfolios.",
        }.get(p.name, p.ai_activity)
print("echo seed: done")
