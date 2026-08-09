"""Persona portraits reach the Agents directory, or the card says who it is.

Two defects made every card a blank grey circle:

1. **The asset fetch used the API base URL.** HomePilot mounts ``/files`` at its
   application root, while the API base conventionally carries the ``/api``
   prefix (the default is ``http://homepilot:7860/api``). Joining an asset path
   onto that produced ``/api/files/projects/.../thumb_avatar_x.webp``, which is
   a 404 — so the proxy returned nothing for every persona on every install
   using the prefixed form.

2. **The card had no fallback for a failed load.** The `<img>` onError handler
   hid the image and rendered nothing in its place. A missing portrait was
   supposed to fall back to the agent's initials (docs/agents-ui.md), and did —
   but only when there was no URL at all, never when the URL failed.

A third, quieter one: a sync overwrote ``snapshot_json`` wholesale, deleting the
embedded portrait of an agent imported from a ``.hpersona`` package.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from daypilot_knowledge.db import HomePilotAgentLink, create_engine_from_settings, session_scope
from daypilot_orchestrator.homepilot.client import HomePilotClient
from daypilot_orchestrator.homepilot.sync import sync_agents

FIX = Path(__file__).resolve().parent / "fixtures" / "homepilot"

# A one-pixel WebP stands in for a 256px persona thumbnail.
_IMAGE = b"RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x00"
THUMB_REF = "projects/scarlett-project-id/persona/appearance/thumb_avatar_scarlett.webp"


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _ws() -> str:
    return "ws-hp-" + uuid.uuid4().hex[:8]


def _client(base_url: str, *, serve: str = f"/files/{THUMB_REF}",
            content_type: str = "image/webp") -> tuple[HomePilotClient, list[str]]:
    """A client that records every URL it asks for and serves one known asset."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.path == serve:
            return httpx.Response(200, content=_IMAGE, headers={"content-type": content_type})
        return httpx.Response(404, text="Not Found")

    return HomePilotClient(base_url=base_url, api_key="hp-key",
                           transport=httpx.MockTransport(handler)), asked


# ── Assets are served from the origin, not from under the API prefix ────────

@pytest.mark.parametrize("base_url,expected", [
    # The documented default. This is the shape that was broken.
    ("http://homepilot:7860/api", "http://homepilot:7860"),
    ("http://localhost:8000/api/", "http://localhost:8000"),
    # An API already at the root is left alone.
    ("http://localhost:8000", "http://localhost:8000"),
    # A HomePilot behind a reverse proxy keeps its mount point — only the /api
    # segment goes, because its files live at <mount>/files, not at the host root.
    ("https://example.test/homepilot/api", "https://example.test/homepilot"),
])
def test_the_asset_base_drops_only_the_api_segment(base_url, expected):
    assert HomePilotClient(base_url=base_url).asset_base_url() == expected


def test_a_thumbnail_is_fetched_from_the_root_not_from_slash_api():
    """The regression itself: /api/files/... is a 404 on every HomePilot."""
    client, asked = _client("http://homepilot:7860/api")
    found = client.asset(THUMB_REF)

    assert found is not None, "the portrait must be found via the asset origin"
    assert found == (_IMAGE, "image/webp")
    assert asked == [f"http://homepilot:7860/files/{THUMB_REF}"]
    assert "/api/files/" not in asked[0]


def test_an_already_rooted_reference_is_not_prefixed_twice():
    """Some personas store the ref as `/files/...` rather than a bare path."""
    client, asked = _client("http://localhost:8000")
    assert client.asset(f"/files/{THUMB_REF}") is not None
    assert asked == [f"http://localhost:8000/files/{THUMB_REF}"]


def test_a_missing_asset_is_none_rather_than_an_exception():
    client, _ = _client("http://homepilot:7860/api")
    assert client.asset("projects/nope/persona/appearance/thumb_avatar_gone.webp") is None


def test_an_html_error_page_is_not_served_as_a_portrait():
    """A 200 carrying an auth error page would render as a broken image."""
    client, _ = _client("http://homepilot:7860/api", content_type="text/html")
    assert client.asset(THUMB_REF) is None


def test_an_unreachable_homepilot_is_none_not_a_crash():
    def boom(_req):
        raise httpx.ConnectError("refused")

    client = HomePilotClient(base_url="http://down:7860/api", transport=httpx.MockTransport(boom))
    assert client.asset(THUMB_REF) is None


def test_an_empty_reference_asks_for_nothing():
    client, asked = _client("http://homepilot:7860/api")
    assert client.asset("") is None and client.asset(None) is None  # type: ignore[arg-type]
    assert asked == []


# ── The proxy prefers the thumbnail and falls back to the full portrait ─────

def test_fetch_avatar_prefers_the_thumbnail_and_falls_back(monkeypatch):
    from app import homepilot_platform as hp

    ws = _ws()
    eng = create_engine_from_settings()
    with session_scope(eng) as s:
        link = HomePilotAgentLink(
            workspace_id=ws, connection_id="conn-av", homepilot_project_id="scarlett-project-id",
            name="Scarlett", thumbnail_ref=THUMB_REF,
            avatar_ref="projects/scarlett-project-id/persona/appearance/avatar_scarlett.png",
        )
        s.add(link)
        s.flush()
        link_id = link.id

    client, asked = _client("http://homepilot:7860/api")
    monkeypatch.setattr(hp, "_get_connection", lambda *_a, **_k: object())
    monkeypatch.setattr(hp, "_client_for", lambda _row: client)

    with session_scope(eng) as s:
        assert hp.fetch_avatar(s, ws, link_id) == (_IMAGE, "image/webp")
    # The 256px thumbnail is what the card needs; the full portrait is never
    # downloaded when it is present.
    assert asked == [f"http://homepilot:7860/files/{THUMB_REF}"]

    # Thumbnail gone (persona committed before thumbnails existed) → full portrait.
    full = "projects/scarlett-project-id/persona/appearance/avatar_scarlett.png"
    client2, asked2 = _client("http://homepilot:7860/api", serve=f"/files/{full}", content_type="image/png")
    monkeypatch.setattr(hp, "_client_for", lambda _row: client2)
    with session_scope(eng) as s:
        assert hp.fetch_avatar(s, ws, link_id) == (_IMAGE, "image/png")
    assert asked2[-1] == f"http://homepilot:7860/files/{full}"


# ── A sync must not delete an imported agent's embedded portrait ────────────

class _FakeDiscovery:
    def __init__(self, projects, models):
        self._p, self._m = projects, models

    def list_projects(self):
        return self._p

    def list_models(self):
        return self._m


def test_sync_keeps_an_imported_portrait_in_the_snapshot():
    """`.hpersona` agents carry their picture in snapshot_json; a sync used to
    replace the whole dict and the card went blank on the next pass."""
    ws = _ws()
    projects = _fixture("projects.json")["projects"]
    model_ids = [m["id"] for m in _fixture("models.json")["data"]]
    eng = create_engine_from_settings()
    data_uri = "data:image/png;base64,iVBORw0KGgo="

    with session_scope(eng) as s:
        sync_agents(s, ws, "conn-snap", _FakeDiscovery(projects, model_ids))
    with session_scope(eng) as s:
        link = s.query(HomePilotAgentLink).filter_by(
            workspace_id=ws, homepilot_project_id="scarlett-project-id").one()
        link.snapshot_json = {**(link.snapshot_json or {}), "avatar_data_uri": data_uri}

    with session_scope(eng) as s:
        sync_agents(s, ws, "conn-snap", _FakeDiscovery(projects, model_ids))
    with session_scope(eng) as s:
        link = s.query(HomePilotAgentLink).filter_by(
            workspace_id=ws, homepilot_project_id="scarlett-project-id").one()
        assert link.snapshot_json["avatar_data_uri"] == data_uri  # survived the sync
        assert link.snapshot_json["shared"] is True               # and still refreshed


# ── The card identifies the agent even when the portrait will not load ──────

SRC = Path(__file__).resolve().parents[1] / "packages" / "ui-bridge" / "src" / "agents"


def test_the_portrait_component_falls_back_to_initials_on_a_failed_load():
    portrait = (SRC / "AgentPortrait.tsx").read_text(encoding="utf-8")
    # A load failure flips to initials rather than hiding the image and leaving
    # an empty circle behind.
    assert "onError={() => setFailed(true)}" in portrait
    assert "showImage" in portrait and "agentInitials(name" in portrait
    # A new URL is a new attempt — a re-synced portrait must not stay hidden.
    assert "useEffect(() => { setFailed(false) }, [avatarUrl])" in portrait


def test_every_surface_uses_the_one_portrait_component():
    """Three call sites had three different fallbacks; one had none that worked."""
    for rel in ("AgentCard.tsx", "workspace/AgentWorkspaceHeader.tsx", "workspace/AgentChatPanel.tsx"):
        source = (SRC / rel).read_text(encoding="utf-8")
        assert "<AgentPortrait" in source, f"{rel} still renders its own portrait"
        assert "<img src={agent.avatarUrl}" not in source, f"{rel} still has a raw <img>"


# ── A disabled agent can be turned on from the directory ────────────────────

def test_the_card_can_turn_an_agent_on():
    """Synced agents start disabled by design, so the directory has to offer the
    deliberate act that undoes it. The hook, the client method and the PATCH
    endpoint all existed — nothing rendered a control that called them, so every
    card read "Disabled" with no way forward."""
    card = (SRC / "AgentCard.tsx").read_text(encoding="utf-8")
    assert "onToggleEnabled" in card
    assert "aria-pressed={agent.enabled}" in card
    # Nested in a card that is itself a button — the click must not also open
    # the workspace.
    assert "e.stopPropagation(); onToggleEnabled(agent)" in card
    # Label is text, not colour alone, and says which way it goes.
    assert "'Turn off' : 'Turn on'" in card


def test_the_landing_page_passes_the_toggle_through():
    page = (SRC / "AgentsLandingPage.tsx").read_text(encoding="utf-8")
    assert "toggleEnabled" in page, "useAgents exposes it; the page must consume it"
    assert "onToggleEnabled={toggleEnabled}" in page


def test_the_enable_control_is_styled_and_reachable_by_keyboard():
    css = (SRC / "agents.css").read_text(encoding="utf-8")
    assert ".dp-agentcard__enable" in css
    assert ".dp-agentcard__enable:focus-visible" in css
    assert "min-height: 32px" in css  # touch target on a phone
