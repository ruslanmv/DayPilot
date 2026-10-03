"""Presentations MCP server: protocol handshake, tool listing and calls under the same workspace
scope as the REST API; drafts only, no approval or sending tools."""

import base64
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import presentations as P
from test_presentations import setup_company, story

URL = "/v1/presentations/mcp"


@pytest.fixture(autouse=True)
def flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS", "true")
    monkeypatch.setenv("DAYPILOT_PRESENTATIONS_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(P, "connector_for", lambda s, w: None)


def ws():
    return {"X-Workspace-Id": "ws-" + uuid.uuid4().hex[:8]}


def rpc(c, h, method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method, **({"params": params} if params is not None else {})}
    return c.post(URL, json=body, headers=h)


def call(c, h, name, args):
    r = rpc(c, h, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_handshake_and_tool_list():
    c, h = TestClient(app), ws()
    init = rpc(c, h, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"] and init["serverInfo"]["name"] == "daypilot-presentations"
    assert rpc(c, h, "initialize", {"protocolVersion": "1999-01-01"}).json()["result"]["protocolVersion"] == "2025-06-18"
    assert c.post(URL, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h).status_code == 202
    assert rpc(c, h, "ping").json()["result"] == {}
    tools = rpc(c, h, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"list_brands", "list_decks", "get_deck", "propose_outline", "create_deck", "revise_deck", "regenerate_slides", "prepare_weekly", "export_deck"}
    assert not any(n for n in names if "approve" in n or "send" in n or "share" in n or "deliver" in n)
    assert all(t["inputSchema"]["type"] == "object" and "annotations" in t for t in tools)
    assert c.get(URL, headers=h).status_code == 405


def test_protocol_errors():
    c, h = TestClient(app), ws()
    assert c.post(URL, content=b"{not json", headers={**h, "content-type": "application/json"}).json()["error"]["code"] == -32700
    assert c.post(URL, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}], headers=h).json()["error"]["code"] == -32600
    assert c.post(URL, json={"id": 1, "method": "ping"}, headers=h).json()["error"]["code"] == -32600
    assert rpc(c, h, "resources/list").json()["error"]["code"] == -32601
    assert rpc(c, h, "tools/call", {"name": "approve_deck", "arguments": {}}).json()["error"]["code"] == -32602
    bad = call(c, h, "get_deck", {"deckId": 3})
    assert bad["isError"] and "deckId must be string" in bad["content"][0]["text"]
    assert call(c, h, "get_deck", {})["isError"]
    assert call(c, h, "list_decks", {"surprise": 1})["isError"]
    assert c.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={**h, "Origin": "https://evil.example"}).status_code == 403


def test_full_flow_through_tools():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    brands = call(c, h, "list_brands", {})["structuredContent"]["companies"]
    assert brands[0]["id"] == cid and brands[0]["activeBrandVersion"] == 1
    outline = call(c, h, "propose_outline", {"brief": "Weekly review", "genre": "weekly_update"})["structuredContent"]
    assert outline["mode"] == "template" and outline["storyline"]["slides"]
    created = call(c, h, "create_deck", {"companyId": cid, "storyline": story()})["structuredContent"]
    did = created["id"]
    got = call(c, h, "get_deck", {"deckId": did})["structuredContent"]
    assert got["revision"]["run"]["status"] == "succeeded" and got["files"]["pptx"].endswith("/files/pptx")
    s2 = story()
    s2["slides"][4]["next_steps"] = ["Ship it"]
    revised = call(c, h, "revise_deck", {"deckId": did, "storyline": s2, "expectedRevision": 1})["structuredContent"]
    assert revised["headRevision"] == 2
    stale = call(c, h, "revise_deck", {"deckId": did, "storyline": s2, "expectedRevision": 1})
    assert stale["isError"] and stale["content"][0]["text"].startswith("409")
    exported = call(c, h, "export_deck", {"deckId": did, "revision": 2, "includeContent": True})
    info = exported["structuredContent"]
    assert info["approved"] is False and len(info["sha256"]) == 64
    blob = next(x for x in exported["content"] if x["type"] == "resource")["resource"]
    assert base64.b64decode(blob["blob"])[:2] == b"PK" and blob["mimeType"].endswith("presentationml.presentation")
    decks = call(c, h, "list_decks", {"query": "Weekly"})["structuredContent"]["decks"]
    assert any(d["id"] == did for d in decks)
    assert call(c, h, "regenerate_slides", {"deckId": did, "slideIds": ["close"], "expectedRevision": 2})["isError"]  # no AI connected


def test_tools_respect_workspace_scope():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    did = call(c, h, "create_deck", {"companyId": cid, "storyline": story()})["structuredContent"]["id"]
    other = ws()
    for name, args in (("get_deck", {"deckId": did}), ("export_deck", {"deckId": did, "revision": 1}), ("create_deck", {"companyId": cid, "storyline": story()})):
        r = call(c, other, name, args)
        assert r["isError"] and r["content"][0]["text"].startswith("404"), name
    assert call(c, other, "list_decks", {})["structuredContent"]["decks"] == []


def test_weekly_through_tools_is_idempotent():
    c, h = TestClient(app), ws()
    cid, _ = setup_company(c, h, logo=False)
    sid = c.post("/v1/presentations/series", json={"companyId": cid, "name": "W", "timezone": "UTC", "storyline": story()}, headers=h).json()["id"]
    a = call(c, h, "prepare_weekly", {"seriesId": sid})["structuredContent"]
    b = call(c, h, "prepare_weekly", {"seriesId": sid})["structuredContent"]
    assert a["created"] and not b["created"] and a["deck"]["id"] == b["deck"]["id"]
