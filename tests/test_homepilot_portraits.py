"""Agent portraits survive HomePilot being unreachable or the connection losing its address.

What the directory looked like before: credentials were kept in process memory,
so after a gateway restart a HomePilot connection had no address left. The agents
still listed (they live in DayPilot's database) but every portrait request was a
404, and the page showed nothing but initials with no explanation.

Now every portrait fetched from HomePilot is kept, a sync keeps the ones not yet
seen, and the last good copy is served when HomePilot can't be asked. A 404 says
why in ``X-Portrait-Status``; ``connect`` corrects an address that only works in
its other form (with or without ``/api``).
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app import homepilot_platform as hp
from app.main import app
from daypilot_knowledge.db import HomePilotAgentLink, create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot import portraits
from daypilot_orchestrator.homepilot.client import HomePilotClient

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c636060606000000005000109f60b210000000049454e44ae426082"
)
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00"


@pytest.fixture(autouse=True)
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_SYNC_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_AGENT_PORTRAITS_DIR", str(tmp_path / "portraits"))


def _ws() -> str:
    return "ws-pt-" + uuid.uuid4().hex[:8]


def _link(ws: str, name: str = "Atlas", connection: str = "conn-pt") -> str:
    pid = uuid.uuid4().hex[:8]
    with session_scope(create_engine_from_settings()) as s:
        link = HomePilotAgentLink(
            workspace_id=ws, connection_id=connection, homepilot_project_id=pid, name=name,
            thumbnail_ref=f"projects/{pid}/persona/appearance/thumb_avatar_{name.lower()}.webp",
            avatar_ref=f"projects/{pid}/persona/appearance/avatar_{name.lower()}.png",
        )
        s.add(link)
        s.flush()
        return link.id


def _homepilot(serving: bool = True, *, projects_at: str = "/projects") -> HomePilotClient:
    """A HomePilot that serves every thumbnail (or none) and lists projects at one path."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if serving and path.startswith("/files/") and "thumb_avatar_" in path:
            return httpx.Response(200, content=WEBP, headers={"content-type": "image/webp"})
        if path == projects_at:
            return httpx.Response(200, json={"ok": True, "projects": []})
        if path.endswith("/health"):
            return httpx.Response(200, json={"ok": True, "service": "homepilot-backend"})
        return httpx.Response(404, text="Not Found")

    return HomePilotClient(base_url="http://homepilot.test", api_key="k", transport=httpx.MockTransport(handler))


# ── what is stored ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("data,kind", [
    (PNG, "image/png"),
    (WEBP, "image/webp"),
    (b"\xff\xd8\xff\xe0" + b"0" * 20, "image/jpeg"),
    (b"GIF89a" + b"0" * 10, "image/gif"),
    (b"<!doctype html><html>Not found</html>", None),
    (b"", None),
])
def test_only_real_images_are_recognised(data, kind):
    assert portraits.image_type(data) == kind


def test_html_error_pages_and_oversized_files_are_never_kept():
    assert portraits.save("ws", "l1", "ref", b"<html>error</html>") is False
    assert portraits.save("ws", "l1", "ref", PNG + b"0" * portraits.MAX_BYTES) is False
    assert portraits.load("ws", "l1") is None
    assert portraits.save("ws", "l1", "ref", PNG) is True
    assert portraits.load("ws", "l1") == (PNG, "image/png")
    assert portraits.has("ws", "l1", "ref") and not portraits.has("ws", "l1", "other-ref")
    assert portraits.load("other-ws", "l1") is None  # copies are per workspace


# ── what is served ──────────────────────────────────────────────────────────

def test_a_saved_portrait_is_served_after_the_connection_loses_its_address(monkeypatch):
    ws = _ws()
    link_id = _link(ws)
    monkeypatch.setattr(hp, "_get_connection", lambda *_a: object())
    monkeypatch.setattr(hp, "_client_for", lambda _row: _homepilot())
    with TestClient(app) as gateway:
        live = gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws})
        assert live.status_code == 200 and live.content == WEBP
        assert live.headers["x-portrait-source"] == "live"

        # Gateway restarted with an in-memory credential store: no address left.
        monkeypatch.setattr(hp, "_client_for", lambda _row: None)
        saved = gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws})
        assert saved.status_code == 200 and saved.content == WEBP
        assert saved.headers["x-portrait-source"] == "saved"
        assert saved.headers["x-content-type-options"] == "nosniff"
        assert "max-age=60" in saved.headers["cache-control"]  # ask again soon


def test_a_saved_portrait_is_served_while_homepilot_is_down(monkeypatch):
    ws = _ws()
    link_id = _link(ws)
    monkeypatch.setattr(hp, "_get_connection", lambda *_a: object())
    monkeypatch.setattr(hp, "_client_for", lambda _row: _homepilot())
    with TestClient(app) as gateway:
        assert gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws}).status_code == 200
        monkeypatch.setattr(hp, "_client_for", lambda _row: _homepilot(serving=False))
        down = gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws})
        assert down.status_code == 200 and down.headers["x-portrait-source"] == "saved"


@pytest.mark.parametrize("client,status", [(None, "reconnect"), ("down", "unreachable")])
def test_a_missing_portrait_says_why(monkeypatch, client, status):
    ws = _ws()
    link_id = _link(ws)
    monkeypatch.setattr(hp, "_get_connection", lambda *_a: object())
    monkeypatch.setattr(hp, "_client_for", lambda _row: _homepilot(serving=False) if client else None)
    with TestClient(app) as gateway:
        r = gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws})
    assert r.status_code == 404 and r.headers["x-portrait-status"] == status
    assert r.headers["cache-control"] == "no-store"


def test_a_failing_homepilot_client_never_breaks_the_page(monkeypatch):
    class Broken:
        def asset(self, *_a, **_k):
            raise RuntimeError("boom")

    ws = _ws()
    link_id = _link(ws)
    monkeypatch.setattr(hp, "_get_connection", lambda *_a: object())
    monkeypatch.setattr(hp, "_client_for", lambda _row: Broken())
    with TestClient(app) as gateway:
        assert gateway.get(f"/v1/agents/profiles/{link_id}/avatar", params={"workspaceId": ws}).status_code == 404


# ── sync keeps every portrait, once ─────────────────────────────────────────

def test_sync_keeps_a_copy_of_each_portrait_and_skips_unchanged_ones(monkeypatch):
    ws = _ws()
    ids = [_link(ws, name, connection="conn-sync") for name in ("Atlas", "Diana", "Felix")]
    asked: list[str] = []
    base = _homepilot()

    def counting(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        return base.transport.handle_request(request)

    remote = HomePilotClient(base_url="http://homepilot.test", api_key="k", transport=httpx.MockTransport(counting))
    with session_scope(create_engine_from_settings()) as s:
        assert hp._prefetch_portraits(s, ws, "conn-sync", remote) == 3
        assert hp._prefetch_portraits(s, ws, "conn-sync", remote) == 0  # already kept
    assert len(asked) == 3
    assert all(portraits.load(ws, i) == (WEBP, "image/webp") for i in ids)


def test_a_changed_portrait_gets_a_new_url():
    ws = _ws()
    link_id = _link(ws)
    with session_scope(create_engine_from_settings()) as s:
        link = s.get(HomePilotAgentLink, link_id)
        before = hp._public_profile(link)["avatarUrl"]
        link.thumbnail_ref = link.thumbnail_ref.replace("atlas", "atlas_v2")
        after = hp._public_profile(link)["avatarUrl"]
    assert before != after and before.split("&v=")[0] == after.split("&v=")[0]


# ── connect keeps the address form that lists personas ──────────────────────

@pytest.mark.parametrize("given,projects_at,kept", [
    ("http://homepilot.test/api", "/projects", "http://homepilot.test"),       # backend at the root
    ("http://homepilot.test", "/api/projects", "http://homepilot.test/api"),   # API under /api
    ("http://homepilot.test", "/projects", "http://homepilot.test"),           # already right
])
def test_connect_keeps_the_address_that_lists_personas(monkeypatch, given, projects_at, kept):
    real = HomePilotClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == projects_at:
            return httpx.Response(200, json={"ok": True, "projects": []})
        if request.url.path.endswith("/health"):
            return httpx.Response(404, text="Not Found")  # some installs: reachable, no /health
        return httpx.Response(404, text="Not Found")

    class Local(real):
        def __init__(self, *a, **k):
            k.setdefault("transport", httpx.MockTransport(handler))
            super().__init__(*a, **k)

    monkeypatch.setattr(hp, "HomePilotClient", Local)
    ws = _ws()
    with session_scope(create_engine_from_settings()) as s:
        out = hp.connect(s, ws, given, "k")
        assert out["connection"]["baseUrl"] == kept
