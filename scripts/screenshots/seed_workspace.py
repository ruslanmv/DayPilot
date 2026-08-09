#!/usr/bin/env python3
"""Seed one believable working day for the documentation screenshots.

Not `seed_dev_data.py` — that one creates 5,000 tasks to prove pagination stays
flat, which photographs as noise. This creates the workspace of a single senior
technical leader on a single afternoon: four projects, a planned day, work in
flight, two decisions waiting, and two projects with something to carry over.

Everything lands in the ordinary tables through the ordinary shapes, so every
screen renders it the way it renders a real workspace. Nothing here is written
straight into a view.

Runs against whatever DATABASE_URL is set (a throwaway sqlite for shots).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from daypilot_knowledge.db import (
    AgentRun,
    Approval,
    ChatMessage,
    ChatSession,
    CodingRun,
    DayPlan,
    Document,
    KnowledgeSource,
    PlanBlock,
    Project,
    Task,
    create_engine_from_settings,
    session_scope,
)

WS = "default"

#: Fixed so the shooter can point the browser at this conversation the way a
#: returning user's own browser would — the session and its turns are ordinary
#: rows served by the ordinary endpoint.
CHAT_SESSION_ID = "screenshot-tour-conversation"
CHAT_TITLE = "Standup delivery status"
CHAT_TURNS = [
    ("user", "Where did the standup delivery work get to today?"),
    ("assistant",
     "Thread resolution and the approval lock are done and covered by tests. "
     "What is left is the worker that runs the two jobs unattended. "
     "GitPilot has a patch waiting on your review for the session-ordering fix."),
    ("user", "What needs me before six?"),
    ("assistant",
     "Two decisions: the pull request for the session-ordering fix, and the "
     "revised delivery timeline for Client Alpha. Both are in the Approval "
     "Center — nothing is sent or merged until you decide."),
]

#: name → (repository, risk, progress, ai_activity, next_action, yesterday, today, blocked)
PROJECTS: dict[str, dict] = {
    "DayPilot": {
        "repository": "ruslanmv/DayPilot",
        "risk": "low",
        "progress": 76,
        "ai_activity": "Indexing the standup evidence collector",
        "next_human_action": "Approve the Slack delivery scope",
        "continue_action": "Continue the standup review screen",
        "yesterday": ["Approved the standup review layout",
                      "Landed the evidence drawer"],
        "today": ["Thread-aware Slack delivery", "Worker + lapse healing"],
        "blocked": [],
    },
    "GitPilot Connector": {
        "repository": "ruslanmv/gitpilot",
        "risk": "high",
        "progress": 34,
        "ai_activity": "Re-running the patch suite after the session fix",
        "next_human_action": "Review the authentication boundary",
        "continue_action": "Continue the session ordering work",
        "yesterday": ["Fixed session ordering (newest first)"],
        "today": ["Sandbox execution classifier"],
        "blocked": ["Waiting on the sandbox execution scope"],
    },
    "Client Alpha — Delivery": {
        "repository": "",
        "risk": "medium",
        "progress": 58,
        "ai_activity": "Drafting the revised timeline reply",
        "next_human_action": "Send the revised timeline",
        "continue_action": "Continue the delivery plan",
        "yesterday": ["Collected the open risks"],
        "today": ["Timeline follow-up"],
        "blocked": [],
    },
    "Matrix Designer": {
        "repository": "agent-matrix/matrix-designer",
        "risk": "low",
        "progress": 41,
        "ai_activity": "",
        "next_human_action": "Review the batch roadmap",
        "continue_action": "Continue the roadmap review",
        "yesterday": [],
        "today": [],
        "blocked": [],
    },
}

#: (title, project, start, end, status, priority, owner, source, context)
DAY: list[tuple[str, str, str, str, str, str, str, str, str]] = [
    ("Deep work — standup delivery", "DayPilot", "09:00", "11:30",
     "active", "high", "you", "planner",
     "Thread resolution is done; the worker and its lapse healing are what's left."),
    ("GitPilot patch review", "GitPilot Connector", "11:30", "12:15",
     "scheduled", "high", "you", "gitpilot",
     "Nine files, low risk — the session ordering fix plus its tests."),
    ("Client Alpha — revised timeline", "Client Alpha — Delivery", "14:00", "14:45",
     "scheduled", "medium", "you", "email",
     "Draft is ready in the composer; nothing has been sent."),
    ("Matrix Designer roadmap review", "Matrix Designer", "15:00", "15:45",
     "scheduled", "medium", "you", "design", ""),
    ("Risk alignment", "Client Alpha — Delivery", "16:30", "17:00",
     "scheduled", "medium", "you", "meeting", ""),
]

#: Work that is genuinely stuck, so the blocked state is not decorative.
BLOCKED = [
    ("Sandbox execution scope for GitPilot", "GitPilot Connector",
     "Needs a decision on which commands the sandbox may run."),
]

#: (name, kind, work, project)
RUNNING_AGENTS = [
    ("Project Analyst", "assistant", "Analysing delivery risk across four projects", "Client Alpha — Delivery"),
    ("GitPilot", "coding", "Re-running the patch suite after the session fix", "GitPilot Connector"),
    ("Email Sentinel", "email", "Scanning the inbox for schedule impact", "Client Alpha — Delivery"),
]

#: (action, summary, risk, resource_type, minutes_ago)
APPROVALS = [
    ("git.pr.create", "Open a pull request for the session-ordering fix (9 files, low risk)",
     "medium", "coding_run", 18),
    ("email.send", "Send the revised delivery timeline to Client Alpha",
     "high", "email_draft", 42),
]

#: (title, source, status, project)
DOCUMENTS = [
    ("Client Alpha — delivery plan v4.pdf", "Local PC", "Indexed", "Client Alpha — Delivery"),
    ("DayPilot standup design.md", "Local PC", "Indexed", "DayPilot"),
    ("Q3 architecture review.docx", "Box", "Indexed", None),
    ("GitPilot session notes.md", "Local PC", "Indexing", "GitPilot Connector"),
]

SOURCES = [
    ("local", "Work projects", "/home/ruslan/projects", "read_index", "indexed"),
    ("box", "Client Alpha", "box://clients/alpha", "read_index", "indexed"),
]


def _chat(session, now: datetime) -> None:
    """A short, real conversation so the assistant panel shows its own history."""
    existing = session.get(ChatSession, CHAT_SESSION_ID)
    if existing is not None:
        session.delete(existing)
        session.flush()
    convo = ChatSession(
        id=CHAT_SESSION_ID, workspace_id=WS, title=CHAT_TITLE,
        message_count=len(CHAT_TURNS), last_message_at=now - timedelta(minutes=6),
    )
    session.add(convo)
    session.flush()
    for i, (role, body) in enumerate(CHAT_TURNS):
        session.add(ChatMessage(
            session_id=convo.id, role=role, body=body,
            created_at=now - timedelta(minutes=20 - 4 * i),
        ))
    session.flush()


def _clear(session) -> None:
    """Remove what a previous run seeded so re-running does not double the day.

    Only this script's own rows — the standup seeder owns its evidence and the
    agents seeder owns its personas, and neither should be collateral damage.
    """
    plan = session.query(DayPlan).filter_by(
        workspace_id=WS, plan_date=date.today().isoformat()).first()
    if plan is not None:
        session.delete(plan)
    titles = [d[0] for d in DAY] + [b[0] for b in BLOCKED]
    for task in session.query(Task).filter(Task.workspace_id == WS,
                                           Task.title.in_(titles)).all():
        session.delete(task)
    for run in session.query(AgentRun).filter(
            AgentRun.workspace_id == WS,
            AgentRun.name.in_([a[0] for a in RUNNING_AGENTS])).all():
        session.delete(run)
    for approval in session.query(Approval).filter(
            Approval.workspace_id == WS,
            Approval.action.in_([a[0] for a in APPROVALS])).all():
        session.delete(approval)
    for doc in session.query(Document).filter(
            Document.title.in_([d[0] for d in DOCUMENTS])).all():
        session.delete(doc)
    for src in session.query(KnowledgeSource).filter(
            KnowledgeSource.workspace_id == WS,
            KnowledgeSource.display_name.in_([s[1] for s in SOURCES])).all():
        session.delete(src)
    session.flush()


def _projects(session) -> dict[str, Project]:
    rows: dict[str, Project] = {}
    for name, spec in PROJECTS.items():
        row = session.query(Project).filter_by(workspace_id=WS, name=name).first()
        if row is None:
            row = Project(workspace_id=WS, name=name)
            session.add(row)
        row.repository = spec["repository"]
        row.risk = spec["risk"]
        row.progress = spec["progress"]
        row.ai_activity = spec["ai_activity"]
        row.next_human_action = spec["next_human_action"]
        row.continue_action = spec["continue_action"]
        row.yesterday = list(spec["yesterday"])
        row.today = list(spec["today"])
        row.blocked = list(spec["blocked"])
        rows[name] = row
    session.flush()
    return rows


def seed() -> None:
    engine = create_engine_from_settings()
    today = date.today()
    now = datetime.utcnow()
    # `Task.day` is a weekday name, not a date — the Today engine filters on it
    # and the calendar groups by it.
    weekday = today.strftime("%A")

    with session_scope(engine) as session:
        _clear(session)
        _chat(session, now)
        projects = _projects(session)

        # The day, as tasks. The planner reads these; so does the Today engine,
        # which is what makes Home's "Next priority" the first row below.
        tasks: dict[str, Task] = {}
        for title, project, start, end, status, priority, owner, source, context in DAY:
            task = Task(
                workspace_id=WS, title=title, project_id=projects[project].id,
                start_time=start, end_time=end, status=status, priority=priority,
                owner=owner, source=source, context=context or None,
                day=weekday, updated_at=now,
            )
            session.add(task)
            tasks[title] = task
        for title, project, context in BLOCKED:
            session.add(Task(
                workspace_id=WS, title=title, project_id=projects[project].id,
                status="blocked", priority="high", context=context,
                day=weekday, updated_at=now,
            ))
        session.flush()

        # The plan itself — approved, because a day being photographed at 5pm
        # is a day that was planned this morning.
        plan = DayPlan(workspace_id=WS, plan_date=today.isoformat(), state="ACTIVE",
                       summary="Deep work protected in the morning, meetings batched after lunch.")
        session.add(plan)
        session.flush()
        for i, (title, _project, start, end, status, _p, owner, source, _c) in enumerate(DAY):
            session.add(PlanBlock(
                day_plan_id=plan.id, task_id=tasks[title].id, title=title,
                start_time=start, end_time=end, owner=owner, source=source,
                status="running" if status == "active" else "scheduled", order_index=i,
            ))

        for i, (name, kind, work, project) in enumerate(RUNNING_AGENTS):
            session.add(AgentRun(
                workspace_id=WS, name=name, agent_kind=kind, current_work=work,
                state="running", display_status="Running", project_id=projects[project].id,
                provider="Ollabridge", mode="Local", latency_ms=420 + i * 130,
                updated_at=now - timedelta(minutes=3 * i),
            ))

        for action, summary, risk, resource_type, minutes in APPROVALS:
            session.add(Approval(
                workspace_id=WS, action=action, summary=summary, risk=risk,
                status="pending", resource_type=resource_type,
                created_at=now - timedelta(minutes=minutes),
            ))

        session.add(CodingRun(
            workspace_id=WS, project_id=projects["GitPilot Connector"].id,
            executor="gitpilot", repo="ruslanmv/gitpilot", branch="fix/session-ordering",
            status="awaiting_approval", files_changed=9, risk="low",
            diff_summary="Newest-first session ordering + server-side repo filter",
            updated_at=now - timedelta(minutes=20),
        ))

        for title, source, status, project in DOCUMENTS:
            session.add(Document(
                title=title, source_uri=f"file:///docs/{title}", source=source,
                status=status, ingest_state="indexed" if status == "Indexed" else "queued",
                project_id=projects[project].id if project else None,
            ))

        for provider, name, location, permission, status in SOURCES:
            session.add(KnowledgeSource(
                workspace_id=WS, provider=provider, display_name=name, location=location,
                permission=permission, status=status, last_indexed_at=now - timedelta(hours=2),
            ))

        session.flush()
        print(f"projects: {len(projects)}  blocks: {len(DAY)}  "
              f"agents running: {len(RUNNING_AGENTS)}  approvals: {len(APPROVALS)}")


if __name__ == "__main__":
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("refusing to seed: set DATABASE_URL to a throwaway database")
    seed()
