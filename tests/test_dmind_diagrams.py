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


# --- B0 hardening: archive semantics, documented windows, atomicity, honest upstream errors ---


def tiny(i):
    return {
        "schema_version": "dmind/v1",
        "id": f"d{i}",
        "title": f"Diagram {i}",
        "kind": "mindmap",
        "nodes": [{"id": "n", "label": "Topic"}],
        "edges": [],
    }


def test_ordinary_save_never_unarchives_and_history_is_kept():
    c, headers = client()
    saved = c.post("/v1/diagrams", json={"document": graph()}, headers=headers).json()
    did, doc = saved["id"], saved["document"]
    url = f"/v1/diagrams/{did}"
    r = c.put(url, json={"document": doc, "expectedRevision": 1, "archived": True}, headers=headers)
    assert (r.json()["revision"], r.json()["archived"]) == (2, True)
    # The flag omitted (an ordinary save, an older client) keeps the stored state.
    r = c.put(url, json={"document": doc, "expectedRevision": 2}, headers=headers)
    assert (r.json()["revision"], r.json()["archived"]) == (3, True)
    r = c.put(url, json={"document": doc, "expectedRevision": 3, "archived": False}, headers=headers)
    assert (r.json()["revision"], r.json()["archived"]) == (4, False)
    items = c.get("/v1/diagrams", headers=headers).json()["items"]
    assert len(items) == 1
    original = {k: items[0][k] for k in ("id", "title", "revision", "archived")}  # B0 keys unchanged
    assert original == {"id": did, "title": doc["title"], "revision": 4, "archived": False}
    assert len(c.get(url + "/revisions", headers=headers).json()["items"]) == 4


def test_list_is_newest_first():
    c, headers = client()
    ids = [
        c.post("/v1/diagrams", json={"document": tiny(i)}, headers=headers).json()["id"]
        for i in range(3)
    ]
    first = c.get(f"/v1/diagrams/{ids[0]}", headers=headers).json()
    c.put(
        f"/v1/diagrams/{ids[0]}",
        json={"document": first["document"], "expectedRevision": 1},
        headers=headers,
    )
    listed = [i["id"] for i in c.get("/v1/diagrams", headers=headers).json()["items"]]
    assert listed == [ids[0], ids[2], ids[1]]


def test_documented_windows_return_the_newest_entries_and_keep_the_rest():
    from sqlalchemy import func, select

    from daypilot_knowledge.db import create_engine_from_settings, session_scope
    from daypilot_knowledge.db.models import DiagramRevision

    c, headers = client()
    saved = c.post("/v1/diagrams", json={"document": tiny(0)}, headers=headers).json()
    did, doc = saved["id"], saved["document"]
    for revision in range(1, 102):  # 101 saves -> 102 stored snapshots
        r = c.put(
            f"/v1/diagrams/{did}",
            json={"document": doc, "expectedRevision": revision},
            headers=headers,
        )
        assert r.status_code == 200
    window = c.get(f"/v1/diagrams/{did}/revisions", headers=headers).json()["items"]
    assert [v["revision"] for v in window] == list(range(102, 2, -1))  # newest 100
    with session_scope(create_engine_from_settings()) as session:
        stored = session.execute(
            select(func.count()).select_from(DiagramRevision).where(DiagramRevision.diagram_id == did)
        ).scalar_one()
    assert stored == 102  # older snapshots remain stored beyond the window

    c, headers = client()
    created = [
        c.post("/v1/diagrams", json={"document": tiny(i)}, headers=headers).json()["id"]
        for i in range(201)
    ]
    listed = [i["id"] for i in c.get("/v1/diagrams", headers=headers).json()["items"]]
    assert len(listed) == 200 and listed[0] == created[-1] and created[0] not in listed


def test_failed_snapshot_write_rolls_back_the_new_head(monkeypatch):
    c, headers = client()
    saved = c.post("/v1/diagrams", json={"document": graph()}, headers=headers).json()
    did, original = saved["id"], saved["document"]
    edited = deepcopy(original)
    edited["title"] = "Never persisted"

    def disk_full(**_kwargs):
        raise RuntimeError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(diagrams, "DiagramRevision", disk_full)
        failing = TestClient(app, raise_server_exceptions=False)
        r = failing.put(
            f"/v1/diagrams/{did}",
            json={"document": edited, "expectedRevision": 1},
            headers=headers,
        )
        assert r.status_code == 500
    head = c.get(f"/v1/diagrams/{did}", headers=headers).json()
    assert head["revision"] == 1 and head["document"] == original  # head and snapshot agree
    revisions = c.get(f"/v1/diagrams/{did}/revisions", headers=headers).json()["items"]
    assert [v["revision"] for v in revisions] == [1]
    retry = c.put(
        f"/v1/diagrams/{did}",
        json={"document": edited, "expectedRevision": 1},
        headers=headers,
    )
    assert retry.status_code == 200 and retry.json()["revision"] == 2  # nothing is stuck


def test_oversized_or_invalid_saves_are_rejected_without_side_effects():
    c, headers = client()
    big = graph()
    big["metadata"] = {"pad": "x" * 2_100_000}
    r = c.post("/v1/diagrams", json={"document": big}, headers=headers)
    assert r.status_code == 422 and "2 MB" in r.json()["detail"]
    assert c.get("/v1/diagrams", headers=headers).json()["items"] == []
    saved = c.post("/v1/diagrams", json={"document": graph()}, headers=headers).json()
    broken = deepcopy(saved["document"])
    broken["edges"][0]["target"] = "ghost"
    r = c.put(
        f"/v1/diagrams/{saved['id']}",
        json={"document": broken, "expectedRevision": 1},
        headers=headers,
    )
    assert r.status_code == 422
    assert c.get(f"/v1/diagrams/{saved['id']}", headers=headers).json()["revision"] == 1
    assert len(c.get(f"/v1/diagrams/{saved['id']}/revisions", headers=headers).json()["items"]) == 1


def designer(monkeypatch, handle):
    monkeypatch.setattr(
        diagrams,
        "matrix_designer_from_env",
        lambda: MatrixDesignerAdapter("http://designer", transport=httpx.MockTransport(handle)),
    )


def test_generated_diagrams_are_validated_before_they_reach_the_editor(monkeypatch):
    broken = graph()
    broken["edges"][0]["target"] = "ghost"
    designer(monkeypatch, lambda request: httpx.Response(200, json={"diagram": broken, "mode": "x"}))
    c, headers = client()
    r = c.post("/v1/diagrams/generate", json={"topic": "Order system"}, headers=headers)
    assert r.status_code == 422 and "missing node" in r.json()["detail"]


@pytest.mark.parametrize(
    ("status", "body", "expected", "fragment"),
    [
        (
            400,
            {"detail": "provider 'x' is not in MATRIX_DESIGNER_ALLOWED_PROVIDERS (ollabridge)."},
            422,
            "MATRIX_DESIGNER_ALLOWED_PROVIDERS",
        ),
        (422, {"detail": "unsupported kind or source exceeds 100000 characters"}, 422, "unsupported kind"),
        (422, {"detail": [{"loc": ["body"], "msg": "bad"}]}, 422, "rejected the diagram or source"),
        (401, {"detail": "invalid or missing API key"}, 502, "API key"),
        (500, {}, 502, "request failed"),
        (404, {}, 502, "interoperability update"),
    ],
)
def test_designer_failures_are_explicit_and_actionable(monkeypatch, status, body, expected, fragment):
    designer(monkeypatch, lambda request: httpx.Response(status, json=body))
    c, headers = client()
    for path, payload in (
        ("/v1/diagrams/generate", {"topic": "Order system", "useDesigner": True}),
        ("/v1/diagrams/design-bundle", {"document": graph()}),
    ):
        r = c.post(path, json=payload, headers=headers)
        assert r.status_code == expected and fragment in r.json()["detail"], (path, r.text)


def test_unreachable_designer_points_to_local_mode(monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    designer(monkeypatch, refuse)
    c, headers = client()
    r = c.post("/v1/diagrams/generate", json={"topic": "Order system"}, headers=headers)
    assert r.status_code == 502 and "local outline mode" in r.json()["detail"]
