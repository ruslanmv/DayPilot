"""Offline .hpersona checker + IMPORTS-gated import (Batch A10).

Adding an agent is a HomePilot action; DayPilot only connects. The ONLY way an
agent enters DayPilot from a file is the offline importer, and only behind
DAYPILOT_HOMEPILOT_IMPORTS_ENABLED. These tests lock in the checker (valid /
invalid / dependency report) and that the endpoints 404 unless IMPORTS is on.
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.homepilot import hpersona

client = TestClient(app)


def _ws() -> str:
    return "ws-hp-imp-" + uuid.uuid4().hex[:8]


# A 1x1 PNG — stands in for a bundled persona portrait in the tests.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c636060606000000005000109f60b210000000049454e44ae426082"
)


def _package(*, blueprint_dir: str = "persona", with_avatar: bool = False, **overrides) -> bytes:
    """Build a .hpersona. Older packages nest blueprints under persona/, newer
    ones under blueprint/ — `blueprint_dir` exercises both layouts."""
    manifest = {
        "kind": "homepilot.persona",
        "schema_version": 1,
        "package_version": 1,
        "project_type": "persona",
        "content_rating": "general",
        "source_homepilot_version": "3.0.50",
        "contents": {"name": "Nova", "has_avatar": with_avatar},
        "capability_summary": {"capabilities": ["research", "writing"]},
    }
    manifest.update(overrides.get("manifest", {}))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(f"{blueprint_dir}/persona_agent.json", json.dumps(
            {"label": "Nova", "role": "Researcher", "description": "Finds and summarizes."}))
        zf.writestr(f"{blueprint_dir}/agentic.json", json.dumps({"capabilities": ["research", "writing"]}))
        if with_avatar:
            zf.writestr(f"{blueprint_dir}/persona_appearance.json", json.dumps(
                {"selected_filename": "avatar_nova.png", "selected_thumb_filename": "thumb_nova.png"}))
            zf.writestr("assets/avatar_nova.png", _PNG_1x1)
            zf.writestr("assets/thumb_nova.png", _PNG_1x1)
        zf.writestr("dependencies/tools.json", json.dumps({"tools": [{"name": "web_search"}]}))
        zf.writestr("dependencies/models.json", json.dumps({"image_models": [{"filename": "sdxl.safetensors"}]}))
    return buf.getvalue()


# --- checker (pure) ---------------------------------------------------------

def test_inspect_valid_package_previews_and_lists_dependencies():
    report = hpersona.inspect(_package())
    assert report["valid"] is True and report["errors"] == []
    assert report["preview"]["name"] == "Nova" and report["preview"]["role"] == "Researcher"
    assert "research" in report["preview"]["capabilities"]
    tools = [t["name"] for t in report["dependencies"]["tools"]]
    models = [m["name"] for m in report["dependencies"]["models"]]
    assert "web_search" in tools and "sdxl.safetensors" in models


def test_inspect_rejects_non_zip_and_bad_manifest():
    assert hpersona.inspect(b"not a zip")["errors"] == ["not_a_zip"]
    assert hpersona.inspect(b"")["errors"] == ["empty_file"]
    bad = _package(manifest={"kind": "something.else"})
    report = hpersona.inspect(bad)
    assert report["valid"] is False and "kind_not_persona" in report["errors"]


def test_inspect_never_stores_prompt_or_memory():
    # The preview only carries safe display metadata; no prompt/memory fields.
    report = hpersona.inspect(_package())
    assert set(report["preview"]) <= {"name", "role", "description", "capabilities", "contentRating", "hasAvatar"}


def test_inspect_reads_blueprint_layout_and_reports_avatar():
    # Real gallery packages nest blueprints under blueprint/ and ship a portrait.
    report = hpersona.inspect(_package(blueprint_dir="blueprint", with_avatar=True))
    assert report["valid"] is True
    assert report["preview"]["name"] == "Nova" and report["preview"]["role"] == "Researcher"
    assert report["preview"]["hasAvatar"] is True


# --- IMPORTS gating (endpoints) ---------------------------------------------

def test_add_info_reports_gallery_and_import_state(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.delenv("DAYPILOT_HOMEPILOT_IMPORTS_ENABLED", raising=False)
    r = client.get(f"/v1/homepilot/add-info?workspaceId={_ws()}")
    assert r.status_code == 200
    data = r.json()
    assert data["importsEnabled"] is False and "galleryUrl" in data


def test_hpersona_endpoints_404_without_imports_flag(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.delenv("DAYPILOT_HOMEPILOT_IMPORTS_ENABLED", raising=False)
    r = client.post("/v1/homepilot/hpersona/preview", files={"file": ("a.hpersona", _package())})
    assert r.status_code == 404  # offline import is off by default


def test_hpersona_preview_and_import_behind_flag(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_IMPORTS_ENABLED", "true")
    ws = _ws()
    pkg = _package()

    prev = client.post("/v1/homepilot/hpersona/preview", files={"file": ("nova.hpersona", pkg)})
    assert prev.status_code == 200 and prev.json()["valid"] is True

    imp = client.post(f"/v1/homepilot/hpersona/import?workspaceId={ws}", files={"file": ("nova.hpersona", pkg)})
    assert imp.status_code == 200 and imp.json()["code"] == "imported"

    # The imported agent shows up (disabled + offline until a live HomePilot).
    profiles = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]
    nova = next(p for p in profiles if p["name"] == "Nova")
    assert nova["enabled"] is False and nova["status"] == "offline"


def test_imported_persona_photo_is_served_offline(monkeypatch):
    # A downloaded gallery persona carries its portrait; the imported agent must
    # expose an avatarUrl and the avatar endpoint must serve the image bytes even
    # with no live HomePilot to proxy from.
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_IMPORTS_ENABLED", "true")
    ws = _ws()
    pkg = _package(blueprint_dir="blueprint", with_avatar=True)

    imp = client.post(f"/v1/homepilot/hpersona/import?workspaceId={ws}", files={"file": ("nova.hpersona", pkg)})
    assert imp.status_code == 200 and imp.json()["code"] == "imported"
    link_id = imp.json()["agentId"]

    profiles = client.get(f"/v1/agents/profiles?workspaceId={ws}").json()["profiles"]
    nova = next(p for p in profiles if p["id"] == link_id)
    assert nova["avatarUrl"] == f"/v1/agents/profiles/{link_id}/avatar"

    avatar = client.get(f"/v1/agents/profiles/{link_id}/avatar?workspaceId={ws}")
    assert avatar.status_code == 200
    assert avatar.headers["content-type"].startswith("image/")
    assert avatar.content == _PNG_1x1  # the exact bundled portrait, served locally


def test_hpersona_import_rejects_invalid_package(monkeypatch):
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_HOMEPILOT_IMPORTS_ENABLED", "true")
    r = client.post(f"/v1/homepilot/hpersona/import?workspaceId={_ws()}",
                    files={"file": ("bad.hpersona", b"garbage")})
    assert r.status_code == 422
