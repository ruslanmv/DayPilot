#!/usr/bin/env python3
"""Seed a realistic-volume DayPilot workspace for development and load testing.

Loads thousands of tasks plus projects, documents, agent runs, approvals, and
Today Context events so pagination, filtering, and the scale indexes can be
exercised against representative data.

Usage:
    python scripts/seed_dev_data.py                 # default volume
    python scripts/seed_dev_data.py --tasks 20000   # custom volume
    python scripts/seed_dev_data.py --reset         # delete seeded rows first
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "services" / "knowledge-service"
if str(SERVICE_PATH) not in sys.path:
    sys.path.insert(0, str(SERVICE_PATH))

from daypilot_knowledge.db import (  # noqa: E402
    AgentRun,
    Approval,
    Base,
    CodingRun,
    Document,
    Event,
    Project,
    Task,
    create_engine_from_settings,
    session_scope,
)

WORKSPACE = "default"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
OWNERS = ["you", "ai", "team", "system"]
PRIORITIES = ["critical", "high", "medium", "low"]
TASK_STATUSES = ["active", "running", "scheduled", "blocked", "done", "needs_approval"]
RISKS = ["low", "medium", "high"]
PROJECT_STATUSES = ["On Track", "Active", "At Risk", "Review", "Stable"]
AGENT_KINDS = [
    "Email Sentinel", "GitPilot", "Matrix Designer", "Scheduler",
    "Document Assistant", "Project Analyst",
]
AGENT_STATES = ["queued", "running", "succeeded", "failed", "cancelled"]
DISPLAY_STATUSES = ["Running", "Needs Approval", "Blocked"]
DOC_SOURCES = ["Local PC", "Box", "DayPilot Vault", "Project Folder", "Generated"]
DOC_STATUSES = ["Indexed", "Needs Permission", "Linked to Today", "Not Yet Indexed"]


def _spread(now: datetime, i: int) -> datetime:
    # Spread rows across ~90 days so temporal sorts and cursors are meaningful.
    return now - timedelta(minutes=i * 7)


def seed(*, tasks: int, projects: int, documents: int, agent_runs: int) -> dict[str, int]:
    engine = create_engine_from_settings()
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    rng = random.Random(42)

    with session_scope(engine) as session:
        project_rows = []
        for i in range(projects):
            p = Project(
                workspace_id=WORKSPACE,
                name=f"Project {i:03d}",
                progress=rng.randint(0, 100),
                status=rng.choice(PROJECT_STATUSES),
                risk=rng.choice(RISKS),
                ai_activity=rng.choice(["Idle", "Drafting patch", "Summarizing docs", "Planning"]),
                next_human_action="Review AI output",
                continue_action="Resume where you left off",
                created_at=_spread(now, i * 10),
                updated_at=_spread(now, i * 10),
            )
            project_rows.append(p)
            session.add(p)
        session.flush()
        project_ids = [p.id for p in project_rows]

        for i in range(tasks):
            t = Task(
                workspace_id=WORKSPACE,
                title=f"Task {i:05d}: {rng.choice(['review', 'draft', 'ship', 'plan', 'triage'])}",
                owner=rng.choice(OWNERS),
                executor=rng.choice(["", "GitPilot", "Email Sentinel", "Scheduler"]),
                priority=rng.choice(PRIORITIES),
                status=rng.choice(TASK_STATUSES),
                day=rng.choice(DAYS),
                start_time=f"{rng.randint(7, 18):02d}:00",
                end_time=f"{rng.randint(7, 18):02d}:30",
                context="Seeded task for scale testing.",
                risk=rng.choice(RISKS),
                project_id=rng.choice(project_ids) if project_ids and rng.random() < 0.8 else None,
                created_at=_spread(now, i),
                updated_at=_spread(now, i),
            )
            session.add(t)
            if i % 2000 == 0:
                session.flush()

        for i in range(agent_runs):
            state = rng.choice(AGENT_STATES)
            session.add(
                AgentRun(
                    workspace_id=WORKSPACE,
                    name=rng.choice(AGENT_KINDS),
                    agent_kind=rng.choice(AGENT_KINDS),
                    current_work=f"Working item {i}",
                    state=state,
                    display_status=rng.choice(DISPLAY_STATUSES),
                    model="llama3.1",
                    mode=rng.choice(["Local", "Hybrid", "Cloud"]),
                    latency_ms=rng.randint(80, 3000),
                    project_id=rng.choice(project_ids) if project_ids else None,
                    created_at=_spread(now, i * 3),
                    updated_at=_spread(now, i * 3),
                )
            )

        for i in range(documents):
            session.add(
                Document(
                    source_uri=f"file:///seed/doc_{i:04d}.pdf",
                    title=f"Document {i:04d}",
                    project_id=rng.choice(project_ids) if project_ids else None,
                    status=rng.choice(DOC_STATUSES),
                    source=rng.choice(DOC_SOURCES),
                    ingest_state="indexed",
                    created_at=_spread(now, i * 5),
                )
            )

        for i in range(min(50, tasks)):
            session.add(
                Approval(
                    workspace_id=WORKSPACE,
                    action=rng.choice(["email.send", "git.write", "calendar.create", "file.generate"]),
                    summary="Seeded approval awaiting decision.",
                    risk=rng.choice(RISKS),
                    status=rng.choice(["pending", "approved", "rejected"]),
                    created_at=_spread(now, i * 20),
                )
            )

        for i in range(min(30, agent_runs)):
            session.add(
                CodingRun(
                    workspace_id=WORKSPACE,
                    executor=rng.choice(["gitpilot", "claude_code", "codex"]),
                    repo="ruslanmv/DayPilot",
                    branch=f"seed/branch-{i}",
                    mode="ask",
                    status=rng.choice(["queued", "running", "needs_review", "approved", "merged"]),
                    files_changed=rng.randint(1, 40),
                    tests_passed=rng.randint(0, 200),
                    tests_total=200,
                    risk=rng.choice(RISKS),
                    created_at=_spread(now, i * 25),
                    updated_at=_spread(now, i * 25),
                )
            )

        for i in range(20):
            session.add(
                Event(
                    workspace_id=WORKSPACE,
                    type=rng.choice(
                        ["plan.updated", "block.started", "approval.requested",
                         "agent.state_changed", "blocker.raised"]
                    ),
                    payload_json={"seedIndex": i},
                )
            )

    return {
        "projects": projects,
        "tasks": tasks,
        "agent_runs": agent_runs,
        "documents": documents,
    }


def reset() -> None:
    engine = create_engine_from_settings()
    Base.metadata.create_all(engine)
    with session_scope(engine) as session:
        for model in (Event, CodingRun, Approval, Document, AgentRun, Task, Project):
            session.query(model).filter_by(**({"workspace_id": WORKSPACE} if hasattr(model, "workspace_id") else {})).delete()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed DayPilot dev/load data.")
    parser.add_argument("--tasks", type=int, default=5000)
    parser.add_argument("--projects", type=int, default=40)
    parser.add_argument("--documents", type=int, default=200)
    parser.add_argument("--agent-runs", type=int, default=100)
    parser.add_argument("--reset", action="store_true", help="Delete seeded rows before seeding.")
    args = parser.parse_args()

    if args.reset:
        reset()
        print("Reset seeded rows.")

    counts = seed(
        tasks=args.tasks,
        projects=args.projects,
        documents=args.documents,
        agent_runs=args.agent_runs,
    )
    print(f"Seeded: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
