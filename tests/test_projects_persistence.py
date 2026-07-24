"""Persistent, server-owned Projects (Issue 4).

A created project is stored in the database (survives refresh / other devices),
seeds an actionable task so it can feed planner readiness, and emits a
project.created event + a notification. Update and delete are persisted too.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _ws() -> str:
    return "proj-" + uuid.uuid4().hex[:8]


def test_create_project_persists_and_seeds_a_task():
    ws = _ws()
    resp = client.post("/v1/projects", json={
        "name": "Ollabridge Router", "goal": "route LLM requests with failover",
        "milestone": "Design the failover path", "repository": "git@github:acme/router.git",
        "workspaceId": ws,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Ollabridge Router"
    assert body["createdTasks"] == 1  # first milestone becomes an actionable task
    pid = body["id"]

    # It persists: a fresh GET (new "session"/refresh) still sees it.
    listed = client.get(f"/v1/projects?workspaceId={ws}").json()["items"]
    assert any(p["id"] == pid for p in listed)

    # The milestone task exists and is actionable (feeds planner readiness).
    tasks = client.get(f"/v1/tasks?workspaceId={ws}").json()["items"]
    assert any(t.get("projectId") == pid and t["status"] == "active" for t in tasks)


def test_create_project_emits_notification():
    ws = _ws()
    client.post("/v1/projects", json={"name": "Design System", "workspaceId": ws})
    notifs = client.get(f"/v1/notifications?workspaceId={ws}").json()["notifications"]
    assert any(n["title"] == "Project created" for n in notifs)


def test_create_requires_a_name():
    assert client.post("/v1/projects", json={"name": "  ", "workspaceId": _ws()}).status_code == 422


def test_update_and_delete_project_persist():
    ws = _ws()
    pid = client.post("/v1/projects", json={"name": "Temp", "workspaceId": ws}).json()["id"]

    upd = client.patch(f"/v1/projects/{pid}", json={"progress": 55, "status": "Review"})
    assert upd.status_code == 200 and upd.json()["progress"] == 55 and upd.json()["status"] == "Review"

    assert client.delete(f"/v1/projects/{pid}").status_code == 204
    assert client.get(f"/v1/projects/{pid}").status_code == 404
    assert client.patch(f"/v1/projects/{pid}", json={"progress": 1}).status_code == 404


def test_project_created_event_is_emitted():
    ws = _ws()
    client.post("/v1/projects", json={"name": "Eventful", "workspaceId": ws})
    # The Today Context event stream carries the project.created event.
    events = client.get(f"/v1/events?workspaceId={ws}").json()
    items = events.get("items", events.get("events", []))
    assert any(e.get("type") == "project.created" for e in items)
