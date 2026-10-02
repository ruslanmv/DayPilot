"""Consumer contract, persistent history, conflicts, and workspace boundaries."""

import json
import uuid
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import diagrams
from daypilot_orchestrator.design.dmind_contract import validate_diagram
from daypilot_orchestrator.design.matrix_designer_adapter import MatrixDesignerAdapter


def graph():
    return json.loads(
        (Path(__file__).parents[1] / "packages/dmind-contract/order-system.dmind.json").read_text()
    )


def client():
    return TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def test_save_reopen_conflict_archive_and_restore_are_nondestructive():
    c, headers = client()
    r = c.post("/v1/diagrams", json={"document": graph()}, headers=headers)
    assert r.status_code == 201, r.text
    saved = r.json()
    did = saved["id"]
    doc = saved["document"]
    original = deepcopy(doc)
    assert doc["id"] != graph()["id"]
    doc["title"] = "Edited system"
    r = c.put(f"/v1/diagrams/{did}", json={"document": doc, "expectedRevision": 1}, headers=headers)
    assert r.status_code == 200 and r.json()["revision"] == 2
    assert (
        c.put(
            f"/v1/diagrams/{did}",
            json={"document": original, "expectedRevision": 1},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        c.get(f"/v1/diagrams/{did}", headers=headers).json()["document"]["title"] == "Edited system"
    )
    versions = c.get(f"/v1/diagrams/{did}/revisions", headers=headers).json()["items"]
    assert [v["revision"] for v in versions] == [2, 1]
    assert versions[1]["document"] == original
    r = c.put(
        f"/v1/diagrams/{did}",
        json={"document": original, "expectedRevision": 2, "archived": True},
        headers=headers,
    )
    assert r.json()["revision"] == 3 and r.json()["archived"] is True
    assert len(c.get(f"/v1/diagrams/{did}/revisions", headers=headers).json()["items"]) == 3


def test_cross_workspace_cannot_load_save_or_read_history():
    c, headers = client()
    saved = c.post("/v1/diagrams", json={"document": graph()}, headers=headers).json()
    other = {"X-Workspace-Id": "other"}
    for suffix in ("", "/revisions"):
        assert c.get(f"/v1/diagrams/{saved['id']}{suffix}", headers=other).status_code == 404
    assert (
        c.put(
            f"/v1/diagrams/{saved['id']}",
            json={"document": graph(), "expectedRevision": 1},
            headers=other,
        ).status_code
        == 404
    )
    assert c.get("/v1/diagrams", headers=other).json()["items"] == []


def test_tokens_enforce_readonly_and_workspace_membership(monkeypatch):
    c, headers = client()
    saved = c.post("/v1/diagrams", json={"document": graph()}, headers=headers).json()
    monkeypatch.setenv("DAYPILOT_AUTH_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_AUTH_TOKENS", "read:read_only,write:operator")
    assert c.get("/v1/diagrams").status_code == 401
    assert (
        c.post(
            "/v1/diagrams", json={"document": graph()}, headers={"Authorization": "Bearer read"}
        ).status_code
        == 403
    )
    assert (
        c.get(
            f"/v1/diagrams/{saved['id']}", headers={**headers, "Authorization": "Bearer write"}
        ).status_code
        == 403
    )


def test_session_mode_requires_session(monkeypatch):
    monkeypatch.setenv("DAYPILOT_REQUIRE_SESSION", "true")
    assert TestClient(app).get("/v1/diagrams").status_code == 401


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g["edges"][0].update(target="ghost"),
        lambda g: g["nodes"].append(deepcopy(g["nodes"][0])),
        lambda g: g.update(schema_version="xmind/v1"),
        lambda g: g.update(kind=[]),
        lambda g: g["edges"][0].update(target=[]),
        lambda g: g["nodes"][0].update(position={"x": float("inf"), "y": 0}),
    ],
)
def test_invalid_contract_rejected(mutate):
    d = graph()
    mutate(d)
    with pytest.raises(ValueError):
        validate_diagram(d)


def test_matrix_handoff_uses_real_contract_without_intake(monkeypatch):
    d = graph()
    c, headers = client()
    requests = []

    def handle(request):
        requests.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/bundle"):
            return httpx.Response(
                200,
                json={
                    "bundle": {"schema_version": "matrix.designer.bundle/v1"},
                    "validation": {"status": "needs-repair"},
                },
            )
        return httpx.Response(200, json={"diagram": d, "mode": "outline"})

    monkeypatch.setattr(
        diagrams,
        "matrix_designer_from_env",
        lambda: MatrixDesignerAdapter("http://designer", transport=httpx.MockTransport(handle)),
    )
    assert (
        c.post("/v1/diagrams/generate", json={"topic": "Order system"}, headers=headers).json()[
            "diagram"
        ]
        == d
    )
    response = c.post("/v1/diagrams/design-bundle", json={"document": d}, headers=headers)
    assert response.status_code == 200 and "intake" not in response.json()
    assert requests[1][0] == "/design/diagrams/bundle" and requests[1][1]["diagram"] == d


def test_upstream_unavailable_is_honest(monkeypatch):
    def handle(request):
        return httpx.Response(404)

    monkeypatch.setattr(
        diagrams,
        "matrix_designer_from_env",
        lambda: MatrixDesignerAdapter("http://designer", transport=httpx.MockTransport(handle)),
    )
    c, headers = client()
    response = c.post("/v1/diagrams/generate", json={"topic": "Topic"}, headers=headers)
    assert response.status_code == 502 and "interoperability update" in response.json()["detail"]


def test_cookie_session_requires_membership_role_and_csrf(monkeypatch):
    from app import identity
    from daypilot_knowledge.db import create_engine_from_settings, session_scope
    from daypilot_knowledge.db.models import User, Workspace, WorkspaceMembership

    workspace = "ws-" + uuid.uuid4().hex[:8]
    email = uuid.uuid4().hex + "@example.test"
    with session_scope(create_engine_from_settings()) as session:
        user = User(
            email=email,
            display_name="Diagram editor",
            role="operator",
            password_hash=identity.hash_password("strong-test-password"),
        )
        session.add(user)
        session.flush()
        session.add(Workspace(id=workspace, name="Diagrams", mode="local", created_by=user.id))
        session.flush()
        session.add(WorkspaceMembership(user_id=user.id, workspace_id=workspace, role="operator"))
        session.flush()
        login = identity.local_login(session, email, "strong-test-password")
    monkeypatch.setenv("DAYPILOT_REQUIRE_SESSION", "true")
    c = TestClient(app)
    c.cookies.set("dp_session", login["token"])
    headers = {"X-Workspace-Id": workspace}
    assert c.get("/v1/diagrams", headers=headers).status_code == 200
    assert c.post("/v1/diagrams", json={"document": graph()}, headers=headers).status_code == 403
    headers["X-CSRF-Token"] = login["csrf"]
    assert c.post("/v1/diagrams", json={"document": graph()}, headers=headers).status_code == 201
    assert c.get("/v1/diagrams", headers={"X-Workspace-Id": "outsider"}).status_code == 403
