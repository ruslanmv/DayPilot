"""B2: cursor paging, search, tags, project association and revision paging."""

import uuid
from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app


def doc(title, **meta):
    return {
        "schema_version": "dmind/v1",
        "id": "x",
        "title": title,
        "kind": "mindmap",
        "nodes": [{"id": "n", "label": "Topic"}],
        "edges": [],
        "metadata": meta,
    }


def setup():
    return TestClient(app), {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def create(c, h, title, **meta):
    r = c.post("/v1/diagrams", json={"document": doc(title, **meta)}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_cursor_paging_is_stable_complete_and_unique():
    c, h = setup()
    ids = [create(c, h, f"Diagram {i:02d}")["id"] for i in range(25)]
    seen, cursor, pages = [], None, 0
    while True:
        r = c.get("/v1/diagrams", params={"limit": 10, **({"cursor": cursor} if cursor else {})}, headers=h)
        body = r.json()
        seen += [i["id"] for i in body["items"]]
        pages += 1
        if not body["hasMore"]:
            assert body["nextCursor"] is None
            break
        cursor = body["nextCursor"]
        # A diagram created mid-walk sorts first and must not repeat or hide older ones.
        if pages == 1:
            create(c, h, "Created during paging")
    assert pages == 3 and len(seen) == len(set(seen)) == 25
    assert seen == ids[::-1]  # newest first, nothing skipped
    assert c.get("/v1/diagrams", params={"cursor": "garbage"}, headers=h).status_code == 400


def test_default_listing_is_backwards_compatible_and_light():
    c, h = setup()
    saved = create(c, h, "Only one", tags=["Alpha"])
    body = c.get("/v1/diagrams", headers=h).json()
    assert body["limit"] == 200 and body["hasMore"] is False
    item = body["items"][0]
    assert item["id"] == saved["id"] and "document" not in item  # lists never ship documents
    assert item["tags"] == ["alpha"] and item["projectId"] is None and item["updatedAt"]


def test_search_tags_archive_and_sort_filters():
    c, h = setup()
    a = create(c, h, "Order processing", tags=["Billing", "core"])
    b = create(c, h, "Inventory 100%_done", tags=["core"])
    create(c, h, "Notes", tags=[])
    titles = lambda **p: sorted(  # noqa: E731
        i["title"] for i in c.get("/v1/diagrams", params=p, headers=h).json()["items"]
    )
    assert titles(q="order") == ["Order processing"]
    assert titles(q="ORDER proc") == ["Order processing"]
    assert titles(q="100%_") == ["Inventory 100%_done"]  # wildcards are literals
    assert titles(q="%") == ["Inventory 100%_done"]
    assert titles(q="nothing") == []
    assert titles(tag="core") == ["Inventory 100%_done", "Order processing"]
    assert titles(tag="BILLING") == ["Order processing"]
    assert titles(tag="cor") == []  # whole tags only
    c.put(
        f"/v1/diagrams/{b['id']}",
        json={"document": b["document"], "expectedRevision": 1, "archived": True},
        headers=h,
    )
    assert titles(archived="exclude") == ["Notes", "Order processing"]
    assert titles(archived="only") == ["Inventory 100%_done"]
    assert len(titles()) == 3
    asc = [i["title"] for i in c.get("/v1/diagrams", params={"order": "asc", "sort": "created_at"}, headers=h).json()["items"]]
    assert asc == ["Order processing", "Inventory 100%_done", "Notes"]
    assert c.get("/v1/diagrams", params={"sort": "title"}, headers=h).status_code == 422
    assert a["id"]


def test_tags_are_validated_normalised_and_follow_saves():
    c, h = setup()
    saved = create(c, h, "Tagged", tags=["  Mixed   Case ", "mixed case", "B"])
    assert saved["document"]["metadata"]["tags"] == ["mixed case", "b"]  # document and index agree
    edited = deepcopy(saved["document"])
    edited["metadata"]["tags"] = ["renamed"]
    c.put(f"/v1/diagrams/{saved['id']}", json={"document": edited, "expectedRevision": 1}, headers=h)
    only = lambda t: [i["id"] for i in c.get("/v1/diagrams", params={"tag": t}, headers=h).json()["items"]]  # noqa: E731
    assert only("renamed") == [saved["id"]] and only("b") == []
    for bad in ("text", [1], ["a|b"], [""], ["x" * 41], [f"t{i}" for i in range(21)]):
        r = c.post("/v1/diagrams", json={"document": doc("Bad", tags=bad)}, headers=h)
        assert r.status_code == 422, bad


def test_project_association_is_workspace_scoped():
    from daypilot_knowledge.db import create_engine_from_settings, session_scope
    from daypilot_knowledge.db.models import Project

    c, h = setup()
    pid = "p-" + uuid.uuid4().hex[:8]
    with session_scope(create_engine_from_settings()) as session:
        session.add(Project(id=pid, workspace_id=h["X-Workspace-Id"], name="Launch"))
    linked = create(c, h, "Linked", project_id=pid)
    assert linked["document"]["metadata"]["project_id"] == pid
    other = create(c, h, "Unlinked")
    listed = lambda **p: [i["id"] for i in c.get("/v1/diagrams", params=p, headers=h).json()["items"]]  # noqa: E731
    assert listed(project_id=pid) == [linked["id"]] and other["id"] in listed()
    # An imported copy never inherits a project that is not in this workspace.
    foreign = create(c, h, "Foreign", project_id="not-here")
    assert "project_id" not in foreign["document"]["metadata"]
    # Saving over an unknown project is refused, not silently dropped.
    bad = deepcopy(linked["document"])
    bad["metadata"]["project_id"] = "not-here"
    r = c.put(f"/v1/diagrams/{linked['id']}", json={"document": bad, "expectedRevision": 1}, headers=h)
    assert r.status_code == 422 and "unknown project" in r.json()["detail"]
    # Another workspace cannot see the link either.
    assert c.get("/v1/diagrams", params={"project_id": pid}, headers={"X-Workspace-Id": "other"}).json()["items"] == []


def test_revision_paging_summaries_and_single_fetch():
    c, h = setup()
    saved = create(c, h, "History")
    did, document = saved["id"], saved["document"]
    for n in range(1, 8):
        document["title"] = f"History v{n + 1}"
        document["nodes"].append({"id": f"n{n}", "label": f"Extra {n}"})
        assert c.put(f"/v1/diagrams/{did}", json={"document": document, "expectedRevision": n}, headers=h).status_code == 200
    page = c.get(f"/v1/diagrams/{did}/revisions", params={"limit": 3, "summary": "true"}, headers=h).json()
    assert [r["revision"] for r in page["items"]] == [8, 7, 6]
    assert page["hasMore"] and page["nextBefore"] == 6
    assert all("document" not in r for r in page["items"])
    assert page["items"][0]["title"] == "History v8" and page["items"][0]["nodes"] == 8
    seen = [r["revision"] for r in page["items"]]
    while page["hasMore"]:
        page = c.get(
            f"/v1/diagrams/{did}/revisions",
            params={"limit": 3, "summary": "true", "before": page["nextBefore"]},
            headers=h,
        ).json()
        seen += [r["revision"] for r in page["items"]]
    assert seen == list(range(8, 0, -1))
    one = c.get(f"/v1/diagrams/{did}/revisions/2", headers=h).json()
    assert one["revision"] == 2 and one["document"]["title"] == "History v2"
    assert c.get(f"/v1/diagrams/{did}/revisions/99", headers=h).status_code == 404
    other = {"X-Workspace-Id": "other"}
    assert c.get(f"/v1/diagrams/{did}/revisions/2", headers=other).status_code == 404
    assert c.get(f"/v1/diagrams/{did}/revisions", params={"limit": 0}, headers=h).status_code == 422
    default = c.get(f"/v1/diagrams/{did}/revisions", headers=h).json()["items"]
    assert len(default) == 8 and "document" in default[0] and default[0]["createdAt"]
