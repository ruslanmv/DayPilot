"""B7: read-only expiring share links: off by default, redacted, revocable, isolated, audited."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import _get_sessionmaker
from app.main import app
from app.routers import diagram_shares as shares
from daypilot_knowledge.db import AuditLog
from daypilot_knowledge.db.models import DiagramShare


@pytest.fixture(autouse=True)
def sharing_on(monkeypatch):
    monkeypatch.setenv("DAYPILOT_DMIND_SHARING", "true")


def doc(title="Plan"):
    return {
        "schema_version": "dmind/v1",
        "id": "x",
        "title": title,
        "kind": "mindmap",
        "nodes": [
            {"id": "root", "label": "Root", "notes": "secret notes", "metadata": {"internal": "x"}},
            {"id": "a", "label": '<script>alert(1)</script>"', "notes": "</p><b>n</b>"},
        ],
        "edges": [{"id": "e1", "source": "root", "target": "a", "kind": "branch"}],
        "metadata": {"sources": [{"name": "private.docx"}], "project_id": None},
    }


def setup():
    c = TestClient(app)
    h = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    d = c.post("/v1/diagrams", json={"document": doc()}, headers=h)
    assert d.status_code == 201, d.text
    return c, h, d.json()["id"]


def share(c, h, did, **body):
    r = c.post(f"/v1/diagrams/{did}/shares", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_nothing_is_shared_unless_enabled(monkeypatch):
    c, h, did = setup()
    monkeypatch.setenv("DAYPILOT_DMIND_SHARING", "false")
    assert c.post(f"/v1/diagrams/{did}/shares", json={}, headers=h).status_code == 404
    assert c.get(f"/v1/diagrams/{did}/shares/preview", headers=h).status_code == 404
    assert c.get("/v1/shared/anything").status_code == 404


def test_link_is_read_only_redacted_and_pinned_to_a_revision():
    c, h, did = setup()
    s = share(c, h, did)
    assert "token" in s and s["state"] == "active" and s["includeNotes"] is False
    body = c.get(f"/v1/shared/{s['token']}").json()
    assert body["readOnly"] is True and body["revision"] == 1
    d = body["document"]
    assert all("notes" not in n and "metadata" not in n for n in d["nodes"])
    assert "metadata" not in d and "private.docx" not in str(body)
    # Later edits are not exposed through an existing link.
    changed = doc("Changed")
    changed["nodes"][0]["label"] = "Edited"
    assert c.put(f"/v1/diagrams/{did}", json={"document": changed, "expectedRevision": 1}, headers=h).status_code == 200
    again = c.get(f"/v1/shared/{s['token']}").json()["document"]
    assert again["title"] == "Plan" and again["nodes"][0]["label"] == "Root"
    # Viewers cannot mutate through the link.
    for method in ("put", "post", "delete", "patch"):
        assert getattr(c, method)(f"/v1/shared/{s['token']}").status_code in (404, 405)


def test_notes_only_when_included_and_preview_matches_what_viewers_get():
    c, h, did = setup()
    preview = c.get(f"/v1/diagrams/{did}/shares/preview", params={"includeNotes": "true"}, headers=h).json()
    s = share(c, h, did, includeNotes=True)
    got = c.get(f"/v1/shared/{s['token']}").json()["document"]
    assert got == preview["document"]
    assert got["nodes"][0]["notes"] == "secret notes" and "metadata" not in got["nodes"][0]
    plain = c.get(f"/v1/diagrams/{did}/shares/preview", headers=h).json()["document"]
    assert all("notes" not in n for n in plain["nodes"])


def test_html_view_escapes_everything_and_sets_strict_headers():
    c, h, did = setup()
    s = share(c, h, did, includeNotes=True)
    r = c.get(s["path"])
    assert r.status_code == 200 and "<script>" not in r.text and "&lt;script&gt;" in r.text
    assert "</p><b>" not in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]


def test_revoke_and_expiry_look_the_same_as_an_unknown_link():
    c, h, did = setup()
    s = share(c, h, did)
    assert c.delete(f"/v1/diagrams/{did}/shares/{s['id']}", headers=h).json()["state"] == "revoked"
    gone = c.get(f"/v1/shared/{s['token']}")
    unknown = c.get("/v1/shared/" + "x" * 43)
    assert gone.status_code == unknown.status_code == 404 and gone.json() == unknown.json()
    assert c.delete(f"/v1/diagrams/{did}/shares/{s['id']}", headers=h).json()["state"] == "revoked"  # idempotent
    s2 = share(c, h, did, expiresInHours=1)
    with _get_sessionmaker()() as session:
        row = session.get(DiagramShare, s2["id"])
        row.expires_at = shares.now() - timedelta(seconds=1)
        session.commit()
    assert c.get(f"/v1/shared/{s2['token']}").status_code == 404
    listed = c.get(f"/v1/diagrams/{did}/shares", headers=h).json()["items"]
    assert {i["id"]: i["state"] for i in listed} == {s["id"]: "revoked", s2["id"]: "expired"}


def test_token_is_never_stored_or_listed():
    c, h, did = setup()
    s = share(c, h, did)
    assert all("token" not in i for i in c.get(f"/v1/diagrams/{did}/shares", headers=h).json()["items"])
    with _get_sessionmaker()() as session:
        row = session.get(DiagramShare, s["id"])
        assert row.token_hash == shares.token_hash(s["token"]) and s["token"] not in str(row.__dict__)


def test_tenant_isolation_for_create_list_preview_and_revoke():
    c, h, did = setup()
    other = {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}
    s = share(c, h, did)
    assert c.post(f"/v1/diagrams/{did}/shares", json={}, headers=other).status_code == 404
    assert c.get(f"/v1/diagrams/{did}/shares", headers=other).status_code == 404
    assert c.get(f"/v1/diagrams/{did}/shares/preview", headers=other).status_code == 404
    assert c.delete(f"/v1/diagrams/{did}/shares/{s['id']}", headers=other).status_code == 404
    assert c.get(f"/v1/shared/{s['token']}").status_code == 200  # still active for its owner's viewers


def test_bounds_and_archived_diagrams():
    c, h, did = setup()
    for bad in ({"expiresInHours": 0}, {"expiresInHours": 24 * 90 + 1}, {"includeNotes": "maybe"}):
        assert c.post(f"/v1/diagrams/{did}/shares", json=bad, headers=h).status_code == 422
    for _ in range(shares.MAX_ACTIVE_PER_DIAGRAM):
        share(c, h, did)
    assert c.post(f"/v1/diagrams/{did}/shares", json={}, headers=h).status_code == 409
    c2, h2, did2 = setup()
    cur = c2.get(f"/v1/diagrams/{did2}", headers=h2).json()
    c2.put(f"/v1/diagrams/{did2}", json={"document": cur["document"], "expectedRevision": cur["revision"], "archived": True}, headers=h2)
    assert c2.post(f"/v1/diagrams/{did2}/shares", json={}, headers=h2).status_code == 409


def test_audit_trail_has_events_but_never_the_token():
    c, h, did = setup()
    s = share(c, h, did)
    c.get(f"/v1/shared/{s['token']}")
    c.delete(f"/v1/diagrams/{did}/shares/{s['id']}", headers=h)
    with _get_sessionmaker()() as session:
        rows = session.execute(select(AuditLog).where(AuditLog.event_type.like("diagram.share.%"))).scalars().all()
        mine = [r for r in rows if r.payload_json.get("shareId") == s["id"]]
        assert sorted(r.event_type for r in mine) == ["diagram.share.created", "diagram.share.revoked", "diagram.share.viewed"]
        assert all(s["token"] not in str(r.payload_json) for r in mine)
        assert session.get(DiagramShare, s["id"]).views == 1


def test_deep_chain_renders_without_exhausting_the_stack():
    c, h, _ = setup()
    nodes = [{"id": f"n{i}", "label": f"L{i}"} for i in range(900)]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i+1}", "kind": "branch"} for i in range(899)]
    d = doc()
    d["nodes"], d["edges"] = nodes, edges
    did = c.post("/v1/diagrams", json={"document": d}, headers=h).json()["id"]
    s = share(c, h, did)
    r = c.get(s["path"])
    assert r.status_code == 200 and "L899" in r.text
