#!/usr/bin/env python3
"""Seed a realistic Daily Standup day for documentation screenshots.

Runs the *real* engine — a workflow, real tasks and runs, then the actual
collector and compiler — so the screenshots show what the product produces
rather than hand-written marketing copy. If a bullet in the docs looks wrong,
the code is wrong.

Runs against whatever DATABASE_URL is set (a throwaway sqlite for shots).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from daypilot_knowledge.db import (
    AgentRun,
    Approval,
    CodingRun,
    IntegrationConnection,
    Project,
    StandupEvidence,
    Task,
    create_engine_from_settings,
    session_scope,
)
from daypilot_orchestrator.integrations.credentials import credential_store
from daypilot_orchestrator.standup import service

WS = "default"
CONN_ID = "demo-slack"

#: A day of real work on the standup feature itself — every line below becomes
#: evidence, and the draft in the screenshot is compiled from it.
COMPLETED_TASKS = [
    "Fix persona portrait loading across the agents directory and workspace",
    "Add a reusable portrait component with an initials fallback",
    "Preserve imported portrait data during agent synchronization",
]
IN_PROGRESS_TASKS = [
    "Thread-aware Slack delivery for the Daily Standup workflow",
]
BLOCKED_TASKS = [
    "Recurring workflow schedules are not represented in the data model",
]


def _slack_connection(session) -> None:
    """A connected Slack, so the setup screen renders in its normal state."""
    if session.get(IntegrationConnection, CONN_ID) is not None:
        return
    conn = IntegrationConnection(
        id=CONN_ID, workspace_id=WS, provider="slack", status="connected",
        auth_type="oauth", capabilities=["chat.read", "chat.send", "chat.history"],
        detail="ok", last_activity_at=datetime.utcnow(),
    )
    session.add(conn)
    session.flush()
    credential_store().put(CONN_ID, {"bot_token": "xoxb-demo-not-a-real-token"})


def _reset(session) -> None:
    """Clear what a previous run seeded, so re-running does not double the day.

    Task ids are random, so a second run would create a second set of rows with
    different dedupe keys — and the evidence drawer would show every item
    twice. Screenshots taken from that would misrepresent the product.
    """
    titles = [*COMPLETED_TASKS, *IN_PROGRESS_TASKS, *BLOCKED_TASKS]
    for task in session.query(Task).filter(Task.workspace_id == WS,
                                           Task.title.in_(titles)).all():
        session.delete(task)
    for run in session.query(AgentRun).filter(AgentRun.workspace_id == WS,
                                              AgentRun.name == "Portrait sync").all():
        session.delete(run)
    for run in session.query(CodingRun).filter(CodingRun.workspace_id == WS,
                                               CodingRun.repo == "ruslanmv/DayPilot").all():
        session.delete(run)
    for approval in session.query(Approval).filter(
            Approval.workspace_id == WS, Approval.action == "slack.chat.send").all():
        session.delete(approval)
    for row in session.query(StandupEvidence).filter(
            StandupEvidence.workspace_id == WS).all():
        session.delete(row)
    session.flush()


def seed() -> None:
    engine = create_engine_from_settings()
    today = date.today()
    now = datetime.utcnow()

    with session_scope(engine) as session:
        _reset(session)
        _slack_connection(session)

        project = session.query(Project).filter_by(workspace_id=WS, name="DayPilot").first()
        if project is None:
            project = Project(workspace_id=WS, name="DayPilot",
                              repository="ruslanmv/DayPilot")
            session.add(project)
            session.flush()

        # Work that actually happened today, spread across the afternoon so the
        # evidence drawer shows a believable timeline rather than one timestamp.
        for offset, title in enumerate(COMPLETED_TASKS):
            session.add(Task(
                workspace_id=WS, title=title, status="done", priority="high",
                project_id=project.id, updated_at=now - timedelta(hours=4 - offset),
            ))
        for title in IN_PROGRESS_TASKS:
            session.add(Task(
                workspace_id=WS, title=title, status="active", priority="high",
                project_id=project.id, updated_at=now - timedelta(minutes=40),
            ))
        for title in BLOCKED_TASKS:
            session.add(Task(
                workspace_id=WS, title=title, status="blocked", priority="medium",
                project_id=project.id, updated_at=now - timedelta(hours=1),
            ))

        session.add(AgentRun(
            workspace_id=WS, name="Portrait sync", agent_kind="assistant",
            current_work="Preserved imported portraits during agent synchronization",
            state="succeeded", display_status="Completed", project_id=project.id,
            updated_at=now - timedelta(hours=2),
        ))
        session.add(CodingRun(
            workspace_id=WS, project_id=project.id, executor="gitpilot",
            repo="ruslanmv/DayPilot", branch="claude/daypilot-production-plan",
            status="applied", files_changed=9, risk="low",
            diff_summary="Persona portrait proxy + initials fallback",
            updated_at=now - timedelta(hours=3),
        ))
        session.add(Approval(
            workspace_id=WS, action="slack.chat.send",
            summary="Post the daily standup update to #daily-standup",
            risk="medium", status="pending", resource_type="integration_action",
            created_at=now - timedelta(minutes=25),
        ))
        session.flush()

        workflow = service.get_workflow_row(
            session, WS,
            (service.list_workflows(session, WS) or [{"id": ""}])[0]["id"],
        ) if service.list_workflows(session, WS) else None
        if workflow is None:
            created = service.create_workflow(session, WS, {
                "name": "Daily Standup",
                "slackConnectionId": CONN_ID,
                "slackChannelId": "C08DAILYSTANDUP",
                "slackChannelName": "daily-standup",
                "timezone": "Europe/Rome",
                "reviewTime": "18:00",
                "reminderTime": "09:00",
                "deliveryMode": "next_workday",
            })
            workflow = service.get_workflow_row(session, WS, created["id"])

        # The real pipeline, not a fixture: collect, then compile.
        service.collect_evidence(session, workflow, today)
        draft = service.generate_draft(session, workflow, today)

        print(f"workflow: {workflow.id}")
        print(f"draft:    {draft.id}  ({draft.status})")
        print(f"posts to: {draft.target_standup_date} in #{workflow.slack_channel_name}")
        print("---")
        print(draft.yesterday_text)
        print(draft.today_text)
        print(draft.blockers_text)


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("refusing to seed: set DATABASE_URL to a throwaway database")
    seed()
