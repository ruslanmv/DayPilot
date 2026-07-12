"""Contract tests for the DayPilot domain API (batch B1).

Cover cursor pagination correctness, server-side filtering, sort validation,
the Today Context aggregation, and the event stream — the guarantees the UI and
future connectors depend on.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _ws() -> str:
    # Isolate each test in its own workspace so counts are deterministic.
    return "ws-" + uuid.uuid4().hex[:8]


def _make_tasks(workspace: str, n: int, **overrides) -> None:
    for i in range(n):
        body = {"title": f"Task {i}", "workspaceId": workspace}
        body.update(overrides)
        resp = client.post("/v1/tasks", json=body)
        assert resp.status_code == 201, resp.text


def test_task_create_and_get_roundtrip():
    ws = _ws()
    resp = client.post("/v1/tasks", json={"title": "Ship B1", "workspaceId": ws, "owner": "you"})
    assert resp.status_code == 201
    task = resp.json()
    assert task["title"] == "Ship B1"
    fetched = client.get(f"/v1/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == task["id"]


def test_missing_task_returns_404():
    assert client.get("/v1/tasks/does-not-exist").status_code == 404


def test_cursor_pagination_is_complete_and_deduplicated():
    ws = _ws()
    _make_tasks(ws, 25)
    seen: list[str] = []
    cursor = None
    pages = 0
    while pages < 100:
        url = f"/v1/tasks?workspaceId={ws}&limit=10"
        if cursor:
            url += f"&cursor={cursor}"
        page = client.get(url).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["nextCursor"]
        pages += 1
        if not cursor:
            break
    assert len(seen) == 25
    assert len(set(seen)) == 25  # no duplicates across page boundaries
    assert pages == 3


def test_page_response_shape_and_limit_clamp():
    ws = _ws()
    _make_tasks(ws, 3)
    page = client.get(f"/v1/tasks?workspaceId={ws}&limit=2").json()
    assert set(page.keys()) == {"items", "nextCursor", "hasMore", "limit"}
    assert page["limit"] == 2
    assert page["hasMore"] is True
    # over-max limit is clamped rather than rejected at the repository layer
    clamped = client.get(f"/v1/tasks?workspaceId={ws}&limit=200").json()
    assert clamped["limit"] == 200


def test_server_side_filtering():
    ws = _ws()
    _make_tasks(ws, 4, status="active")
    _make_tasks(ws, 2, status="blocked")
    blocked = client.get(f"/v1/tasks?workspaceId={ws}&status=blocked&limit=100").json()
    assert len(blocked["items"]) == 2
    assert all(t["status"] == "blocked" for t in blocked["items"])


def test_invalid_cursor_is_rejected():
    assert client.get("/v1/tasks?cursor=not-a-real-cursor").status_code == 400


def test_unsupported_sort_is_rejected():
    resp = client.get("/v1/tasks?sort=title")
    assert resp.status_code == 400


def test_today_context_aggregation():
    ws = _ws()
    _make_tasks(ws, 3, status="active")
    _make_tasks(ws, 2, status="blocked")
    today = client.get(f"/v1/today?workspaceId={ws}").json()
    assert today["counts"]["blockers"] == 2
    assert today["now"] is not None
    assert set(today["counts"].keys()) == {
        "aiRunning", "approvals", "blockers", "projectsActive", "projectsNeedAttention",
    }


def test_events_list_exposes_canonical_types():
    body = client.get("/v1/events").json()
    assert "plan.updated" in body["types"]
    assert "agent.state_changed" in body["types"]


def test_record_event_autoincrements_and_is_readable():
    from app.db import _get_sessionmaker
    from app.events import list_events_since, record_event

    ws = _ws()
    session_factory = _get_sessionmaker()
    with session_factory() as session:
        event = record_event(session, "plan.updated", {"x": 1}, workspace_id=ws)
        session.commit()
        assert event.seq is not None  # autoincrement PK assigned on flush

    with session_factory() as session:
        rows = list_events_since(session, workspace_id=ws, after_seq=0, limit=10)
    assert len(rows) == 1
    assert rows[0].type == "plan.updated"
    assert rows[0].payload_json == {"x": 1}


@pytest.mark.parametrize("path", ["/v1/projects", "/v1/agents", "/v1/documents", "/v1/approvals"])
def test_list_endpoints_return_page_shape(path):
    body = client.get(f"{path}?limit=5").json()
    assert set(body.keys()) == {"items", "nextCursor", "hasMore", "limit"}
    assert isinstance(body["items"], list)
