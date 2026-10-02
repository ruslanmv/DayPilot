"""C4: pushing a map's tasks to the task list is explicit, bounded, idempotent and tenant-isolated."""

import uuid

from fastapi.testclient import TestClient

from app.main import app


def setup():
    c = TestClient(app)
    h = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    d = c.post("/v1/diagrams", json={"document": {
        "schema_version": "dmind/v1", "id": "x", "title": "P", "kind": "mindmap",
        "nodes": [{"id": "root", "label": "Root"}], "edges": []}}, headers=h).json()["id"]
    return c, h, d


def items(n=2):
    return [{"id": f"t{i}", "title": f"Task {i}", "context": "Plan › Build", "due": "2026-03-07", "priority": "high"} for i in range(n)]


def count(c, h):
    r = c.get("/v1/tasks", params={"workspaceId": h["X-Workspace-Id"], "limit": 200}, headers=h).json()
    return r["items"] if "items" in r else r


def test_push_creates_tasks_once_and_lists_them_in_the_task_list():
    c, h, d = setup()
    r = c.post(f"/v1/diagrams/{d}/tasks", json={"items": items(3)}, headers=h)
    assert r.json() == {"created": 3, "skipped": 0}
    again = c.post(f"/v1/diagrams/{d}/tasks", json={"items": items(4)}, headers=h).json()
    assert again == {"created": 1, "skipped": 3}
    tasks = count(c, h)
    assert len(tasks) == 4 and all(t["priority"] == "high" for t in tasks)
    assert {t["title"] for t in tasks} == {f"Task {i}" for i in range(4)}


def test_validation_and_isolation():
    c, h, d = setup()
    bad = [{"items": []}, {"items": items(201)}, {"items": [{"id": "a b", "title": "x"}]}, {"items": [{"id": "a", "title": ""}]},
           {"items": [{"id": "a", "title": "x", "due": "March"}]}, {"items": [{"id": "a", "title": "x", "priority": "urgent"}]}]
    for body in bad:
        assert c.post(f"/v1/diagrams/{d}/tasks", json=body, headers=h).status_code == 422
    other = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    assert c.post(f"/v1/diagrams/{d}/tasks", json={"items": items(1)}, headers=other).status_code == 404
    assert c.post("/v1/diagrams/ghost/tasks", json={"items": items(1)}, headers=h).status_code == 404
    assert count(c, h) == [] or len(count(c, h)) == 0
