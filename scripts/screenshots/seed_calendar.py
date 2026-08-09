#!/usr/bin/env python3
"""Seed a connected Outlook and a day shaped around a real meeting.

Meeting Intelligence only photographs as anything with a calendar attached, so
this seeds the connection the way the OAuth callback does — an ordinary
``IntegrationConnection`` row with calendar capabilities — plus one Outlook
meeting and the prep/focus blocks the day is built around.

It seeds Slack as well, because the meeting-context section is a permission
list: a source whose integration is missing renders disabled, and a screenshot
where every external source is greyed out would not show that distinction.

No credentials are written. Runs against whatever DATABASE_URL is set (a
throwaway sqlite for shots).
"""
import os
from datetime import date, datetime, timedelta

from daypilot_knowledge.db import (
    CalendarEvent, DayPlan, IntegrationConnection, PlanBlock, Project, Task,
    create_engine_from_settings, session_scope,
)
from daypilot_orchestrator.calendar import settings as cal_settings

WS = "default"


def seed() -> None:
    engine = create_engine_from_settings()
    today = date.today()
    now = datetime.utcnow()

    with session_scope(engine) as s:
        for r in s.query(IntegrationConnection).filter_by(workspace_id=WS, provider="microsoft_calendar").all():
            s.delete(r)
        s.add(IntegrationConnection(
            workspace_id=WS, provider="microsoft_calendar", status="connected", auth_type="oauth",
            capabilities=["events.read", "event.read", "freebusy.read"],
            detail="ruslan@company.com", last_activity_at=now - timedelta(minutes=2),
        ))
        # Slack connected so the context section shows a real available source.
        if not s.query(IntegrationConnection).filter_by(workspace_id=WS, provider="slack").first():
            s.add(IntegrationConnection(
                workspace_id=WS, provider="slack", status="connected", auth_type="oauth",
                capabilities=["chat.read"], detail="ok", last_activity_at=now,
            ))
        cal_settings.update_settings(s, WS, {"contextSources": ["projects", "tasks", "documents", "slack"]})

        proj = s.query(Project).filter_by(workspace_id=WS, name="DayPilot").first()
        pid = proj.id if proj else None

        plan = s.query(DayPlan).filter_by(workspace_id=WS, plan_date=today.isoformat()).first()
        if plan is not None:
            s.delete(plan)
            s.flush()
        plan = DayPlan(workspace_id=WS, plan_date=today.isoformat(), state="ACTIVE",
                       summary="Deep work protected, meeting prepared.")
        s.add(plan)
        s.flush()

        DAY = [
            ("Deep work · API gateway", "09:00", "11:00", "planner", "active"),
            ("Prepare · Client Alpha", "11:15", "12:00", "standup", "scheduled"),
            ("Client Alpha architecture review", "14:00", "15:00", "meeting", "scheduled"),
        ]
        for i, (title, start, end, source, status) in enumerate(DAY):
            t = Task(workspace_id=WS, title=title, project_id=pid, start_time=start, end_time=end,
                     status=status, priority="high", owner="you", source=source,
                     day=today.strftime("%A"), updated_at=now)
            s.add(t)
            s.flush()
            s.add(PlanBlock(day_plan_id=plan.id, task_id=t.id, title=title, start_time=start,
                            end_time=end, owner="you", source=source, status=status, order_index=i))

        s.add(CalendarEvent(
            workspace_id=WS, external_id="ms-alpha-review", title="Client Alpha architecture review",
            start_at=datetime.combine(today, datetime.min.time()) + timedelta(hours=14),
            end_at=datetime.combine(today, datetime.min.time()) + timedelta(hours=15),
            source="microsoft_calendar", status="confirmed", location="Microsoft Teams",
        ))
    print(f"calendar seeded: Outlook connected, {len(DAY)} blocks")


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("refusing to seed: set DATABASE_URL to a throwaway database")
    seed()
