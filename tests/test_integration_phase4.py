"""Phase 4 — more providers, unified notifications, cross-integration workflows.

Proves the completion criteria: at least three provider types register behind one
interface, events normalize into one notification center with per-integration
rules, the same approval model applies, and a cross-integration workflow runs.
"""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import Task, create_engine_from_settings, session_scope
from daypilot_orchestrator.integrations import notifications as notif
from daypilot_orchestrator.integrations.providers.extra import GitHubProvider, GoogleCalendarProvider
from daypilot_orchestrator.integrations.registry import available_providers
from daypilot_orchestrator.integrations.workflows import available_workflows, run_workflow

client = TestClient(app)
ENGINE = create_engine_from_settings()


def test_at_least_three_provider_types_registered():
    providers = set(available_providers())
    assert {"slack", "github", "calendar"} <= providers  # three real provider types


def _gh_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "ruslanmv"})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(201, json={"number": 42, "state": "open"})
        return httpx.Response(200, json={"full_name": "ruslanmv/DayPilot"})
    return httpx.MockTransport(handler)


def test_github_provider_read_and_write_shape():
    gh = GitHubProvider(transport=_gh_transport())
    gh.connect({"token": "ghp_x"})
    assert gh.execute("repo.read", {"repo": "ruslanmv/DayPilot"})["full_name"] == "ruslanmv/DayPilot"
    pr = gh.execute("pr.create", {"repo": "ruslanmv/DayPilot", "title": "x", "head": "f"})
    assert pr["number"] == 42
    caps = {c.id: c.kind.value for c in gh.list_capabilities()}
    assert caps["repo.read"] == "read" and caps["pr.create"] == "write"


def test_calendar_provider_capabilities():
    cal = GoogleCalendarProvider()
    caps = {c.id: c.kind.value for c in cal.list_capabilities()}
    assert caps["events.read"] == "read" and caps["events.write"] == "write"


def test_events_normalize_and_group_by_severity():
    with session_scope(ENGINE) as s:
        notif.record_notification(s, "ws_p4", notif.normalize("slack", "mention.created", "Mention", "hi", "approval"))
        notif.record_notification(s, "ws_p4", notif.normalize("github", "connection.error", "CI failed", "main", "attention"))
        notif.record_notification(s, "ws_p4", notif.normalize("linkedin", "comment.created", "Comment", "nice", "info"))
    with session_scope(ENGINE) as s:
        counts = notif.summary(s, "ws_p4")
        approvals = notif.list_notifications(s, "ws_p4", severity="approval")
    assert counts == {"approval": 1, "attention": 1, "info": 1}
    assert len(approvals) == 1 and approvals[0]["provider"] == "slack"


def test_notification_rules_are_per_integration():
    assert notif.delivery_for("slack", "mention.created") == notif.IMMEDIATE
    assert notif.delivery_for("slack", "message.received") == notif.DAILY_SUMMARY
    assert notif.delivery_for("calendar", "task.updated") == notif.IMPORTANT_ONLY


def test_cross_integration_workflow_creates_task():
    assert "slack_message_to_task" in available_workflows()
    with session_scope(ENGINE) as s:
        res = run_workflow(s, "slack_message_to_task",
                           {"workspaceId": "ws_wf", "summary": "Client asks about the deadline"})
        assert res["status"] == "ok"
        task = s.get(Task, res["taskId"])
        assert task.source == "slack" and "deadline" in task.title.lower()


def test_workflow_is_opt_in():
    with session_scope(ENGINE) as s:
        res = run_workflow(s, "github_failure_to_notify", {"workspaceId": "ws_wf"}, enabled={"slack_message_to_task"})
    assert res["status"] == "disabled"


def test_notification_endpoints():
    client.post("/v1/workflows/github_failure_to_notify/run",
                json={"workspaceId": "ws_api", "event": {"summary": "build failed"}})
    body = client.get("/v1/notifications", params={"workspaceId": "ws_api"}).json()
    assert body["summary"]["attention"] >= 1
    assert any(n["provider"] == "github" for n in body["notifications"])
    wf = client.get("/v1/workflows").json()
    assert "slack_message_to_task" in wf["workflows"]
