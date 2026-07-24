"""Persistent, server-owned Knowledge Sources (Issue 1).

The Settings buttons do real work: adding a local folder validates a server
path and persists a source (+ enqueues an index job), re-index enqueues another
durable job, remove deletes the grant, and Box is offered only when configured.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _ws() -> str:
    return "ks-" + uuid.uuid4().hex[:8]


def test_list_starts_empty_and_reports_box_availability():
    body = client.get(f"/v1/knowledge/sources?workspaceId={_ws()}").json()
    assert body["sources"] == [] and body["boxAvailable"] is False


def test_add_local_requires_an_existing_server_path():
    ws = _ws()
    # A browser can't hand the server an arbitrary folder — the path must exist.
    bad = client.post("/v1/knowledge/sources/local", json={"path": "/no/such/folder", "workspaceId": ws})
    assert bad.status_code == 404
    assert client.get(f"/v1/knowledge/sources?workspaceId={ws}").json()["sources"] == []


def test_add_local_persists_and_enqueues_index_job():
    ws = _ws()
    folder = Path(tempfile.mkdtemp(prefix="dp-ks-"))
    resp = client.post("/v1/knowledge/sources/local", json={"path": str(folder), "displayName": "Docs", "workspaceId": ws})
    assert resp.status_code == 201
    data = resp.json()
    assert data["source"]["status"] == "queued" and data["jobId"]
    sid = data["source"]["id"]

    # Persisted: a fresh list still shows it.
    sources = client.get(f"/v1/knowledge/sources?workspaceId={ws}").json()["sources"]
    assert any(s["id"] == sid and s["displayName"] == "Docs" for s in sources)

    # The re-index created a durable job (not a blocking HTTP call).
    jobs = client.get(f"/v1/knowledge/sources/{sid}/jobs?workspaceId={ws}").json()["jobs"]
    assert len(jobs) >= 1 and jobs[0]["state"] == "queued"


def test_reindex_and_delete():
    ws = _ws()
    folder = Path(tempfile.mkdtemp(prefix="dp-ks-"))
    sid = client.post("/v1/knowledge/sources/local", json={"path": str(folder), "workspaceId": ws}).json()["source"]["id"]

    ri = client.post(f"/v1/knowledge/sources/{sid}/reindex", json={"workspaceId": ws})
    assert ri.status_code == 200 and ri.json()["jobId"]

    assert client.delete(f"/v1/knowledge/sources/{sid}?workspaceId={ws}").status_code == 204
    assert client.get(f"/v1/knowledge/sources?workspaceId={ws}").json()["sources"] == []
    assert client.post(f"/v1/knowledge/sources/{sid}/reindex", json={"workspaceId": ws}).status_code == 404


def test_box_oauth_is_honest_when_unconfigured(monkeypatch):
    monkeypatch.delenv("BOX_OAUTH_CLIENT_ID", raising=False)
    out = client.post("/v1/knowledge/box/oauth/start", json={"workspaceId": _ws()}).json()
    assert out["available"] is False and out["reason"] == "box_not_configured"
