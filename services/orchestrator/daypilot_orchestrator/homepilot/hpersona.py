"""Offline ``.hpersona`` checker + importer (Batch A10).

The primary way to add an agent is in HomePilot — DayPilot connects to it, it
never imports personas. The ONLY exception is a fully offline install with no
reachable HomePilot: behind ``DAYPILOT_HOMEPILOT_IMPORTS_ENABLED`` a user may
load a ``.hpersona`` package directly. This module is that offline fallback's
checker/importer.

A ``.hpersona`` is a ZIP:

    manifest.json
    blueprint/{persona_agent,persona_appearance,agentic}.json  (older packages: persona/…)
    dependencies/{tools,mcp_servers,a2a_agents,models}.json
    assets/{avatar_<id>.png, thumb_avatar_<id>.webp, …}

``inspect`` validates the manifest and produces a preview + a dependency report
(what the persona needs — image models, tools, MCP servers, A2A agents). It never
raises for bad input: a malformed package returns ``valid=False`` with reasons,
so the UI can show a clean error. ``import_local`` creates a local agent
reference (never a copy of the prompt/memory — the manifest only carries safe
display metadata).
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import zipfile
from typing import Any

from sqlalchemy.orm import Session

from daypilot_knowledge.db import HomePilotAgentLink
from daypilot_knowledge.db.models import utcnow

# The offline importer uses a synthetic connection + account so imported agents
# never blend with a live HomePilot account (multi-account security).
LOCAL_CONNECTION_ID = "local-hpersona"
LOCAL_ACCOUNT_REF = "local:hpersona"

_REQUIRED = ("kind", "schema_version", "package_version", "project_type", "contents")
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB — a persona package is small; reject bombs

# Persona blueprints live under blueprint/ in current packages and under persona/
# in older ones — read either. Image bytes ship under assets/.
_BLUEPRINT_DIRS = ("blueprint/", "persona/")
_AVATAR_MIME = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}
# Embed at most this many bytes of avatar in the local snapshot. The bundled
# thumbnail is a few KB; a full-res avatar can be ~0.5 MB, so this caps DB bloat.
_MAX_EMBED_BYTES = 512 * 1024


def _read_json(zf: zipfile.ZipFile, name: str) -> dict[str, Any]:
    try:
        with zf.open(name) as f:
            return json.loads(f.read().decode("utf-8"))
    except (KeyError, ValueError, UnicodeDecodeError):
        return {}


def _blueprint_json(zf: zipfile.ZipFile, stem: str) -> dict[str, Any]:
    """Read a persona blueprint by stem, trying each supported directory layout."""
    for prefix in _BLUEPRINT_DIRS:
        data = _read_json(zf, prefix + stem)
        if data:
            return data
    return {}


def _asset_bytes(zf: zipfile.ZipFile, names: set[str], filename: str | None) -> bytes | None:
    """Return the bytes of a bundled asset referenced by bare filename, preferring
    the copy under assets/. Returns None if it isn't in the package."""
    if not filename:
        return None
    candidates = [n for n in names if n == filename or n.endswith("/" + filename)]
    candidates.sort(key=lambda n: (not n.startswith("assets/"), len(n)))
    for name in candidates:
        try:
            with zf.open(name) as f:
                return f.read()
        except KeyError:
            continue
    return None


def _embedded_avatar(
    zf: zipfile.ZipFile, names: set[str], appearance: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """Extract the persona's bundled portrait as a ``data:`` URI so an imported
    (offline) agent still shows its photo with no live HomePilot to proxy from.

    Prefers the small thumbnail over the full-res avatar. Returns
    ``(data_uri, avatar_ref, thumbnail_ref)`` — refs are the appearance filenames
    (kept for the live-sync proxy path); ``data_uri`` is None when nothing small
    enough is bundled."""
    avatar_ref = appearance.get("selected_filename") or None
    thumb_ref = appearance.get("selected_thumb_filename") or None
    data_uri: str | None = None
    for ref in (thumb_ref, avatar_ref):
        raw = _asset_bytes(zf, names, ref)
        if not raw or len(raw) > _MAX_EMBED_BYTES:
            continue
        ext = ("." + ref.rsplit(".", 1)[-1].lower()) if ref and "." in ref else ""
        mime = _AVATAR_MIME.get(ext, "application/octet-stream")
        data_uri = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
        break
    return data_uri, avatar_ref, thumb_ref


def decode_avatar_data_uri(value: Any) -> tuple[bytes, str] | None:
    """Decode a stored ``data:<mime>;base64,<payload>`` avatar into (bytes, mime).
    Returns None for anything that isn't a well-formed data URI."""
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    try:
        header, payload = value.split(",", 1)
        mime = header[len("data:"):].split(";", 1)[0] or "application/octet-stream"
        return base64.b64decode(payload), mime
    except (ValueError, binascii.Error):
        return None


def _dep_items(dep: dict[str, Any], names: list[str], included: set[str]) -> list[dict[str, Any]]:
    out = []
    for n in names:
        out.append({"name": n, "status": "included" if n in included else "external"})
    return out


def inspect(data: bytes) -> dict[str, Any]:
    """Validate + preview a ``.hpersona`` package. Never raises."""
    result: dict[str, Any] = {
        "valid": False,
        "errors": [],
        "preview": {},
        "dependencies": {"models": [], "tools": [], "mcpServers": [], "a2aAgents": [], "allSatisfied": True},
        "manifest": {},
    }
    if not data:
        result["errors"].append("empty_file")
        return result
    if len(data) > _MAX_BYTES:
        result["errors"].append("too_large")
        return result
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        result["errors"].append("not_a_zip")
        return result

    names = set(zf.namelist())
    manifest = _read_json(zf, "manifest.json")
    if not manifest:
        result["errors"].append("missing_manifest")
        return result
    result["manifest"] = {k: manifest.get(k) for k in ("kind", "schema_version", "package_version",
                                                        "project_type", "content_rating", "source_homepilot_version")}

    errors: list[str] = []
    for key in _REQUIRED:
        if key not in manifest:
            errors.append(f"missing:{key}")
    if manifest.get("kind") != "homepilot.persona":
        errors.append("kind_not_persona")
    if manifest.get("project_type") not in (None, "persona"):
        errors.append("project_type_not_persona")

    # Preview from the persona definition (safe display metadata only).
    agent = _blueprint_json(zf, "persona_agent.json")
    agentic = _blueprint_json(zf, "agentic.json")
    appearance = _blueprint_json(zf, "persona_appearance.json")
    contents = manifest.get("contents") or {}
    cap_summary = manifest.get("capability_summary") or {}
    capabilities = (
        cap_summary.get("capabilities")
        or agentic.get("capabilities")
        or agent.get("allowed_tools")
        or []
    )
    has_avatar = bool(
        appearance.get("selected_filename")
        or appearance.get("selected_thumb_filename")
        or contents.get("has_avatar")
    )
    result["preview"] = {
        "name": agent.get("label") or contents.get("name") or "Imported persona",
        "role": agent.get("role") or agent.get("category") or "",
        "description": agent.get("description") or contents.get("description") or "",
        "capabilities": [str(c) for c in capabilities][:12],
        "contentRating": manifest.get("content_rating") or "",
        "hasAvatar": has_avatar,
    }

    # Dependency report. Names referenced by the package; "included" if the asset
    # ships inside the ZIP, else "external" (must exist on the runtime).
    tools = _read_json(zf, "dependencies/tools.json")
    mcp = _read_json(zf, "dependencies/mcp_servers.json")
    a2a = _read_json(zf, "dependencies/a2a_agents.json")
    models = _read_json(zf, "dependencies/models.json")

    tool_names = [t.get("name") or t.get("id") or "tool" for t in (tools.get("tools") or [])]
    mcp_names = [s.get("name") or s.get("id") or "server" for s in (mcp.get("servers") or [])]
    a2a_names = [a.get("name") or a.get("id") or "agent" for a in (a2a.get("agents") or [])]
    model_names = [m.get("filename") or m.get("name") or "model"
                   for m in (models.get("image_models") or []) + (models.get("video_models") or [])]

    included = {n.split("/")[-1] for n in names}
    deps = {
        "models": _dep_items(models, model_names, included),
        "tools": [{"name": n, "status": "external"} for n in tool_names],
        "mcpServers": [{"name": n, "status": "external"} for n in mcp_names],
        "a2aAgents": [{"name": n, "status": "external"} for n in a2a_names],
    }
    # DayPilot doesn't run the persona (HomePilot does), so external deps are an
    # advisory, not a hard failure — the package is importable if the manifest is
    # valid. all_satisfied reflects only that nothing is structurally broken.
    deps["allSatisfied"] = not errors
    result["dependencies"] = deps

    result["errors"] = errors
    result["valid"] = not errors
    return result


def import_local(session: Session, workspace_id: str, data: bytes) -> dict[str, Any]:
    """Create a local agent reference from a valid ``.hpersona`` (offline
    fallback). Returns {code, agentId?} — ``invalid`` when the package fails
    inspection. Never stores the persona prompt or memory."""
    report = inspect(data)
    if not report["valid"]:
        return {"code": "invalid", "errors": report["errors"]}

    preview = report["preview"]

    # Extract the bundled portrait so the imported agent shows its photo even
    # though there is no live HomePilot to proxy it from. The thumbnail (a few KB)
    # is embedded in the snapshot; the appearance filenames are kept as refs so a
    # later live sync of the same persona can still proxy the full-res avatar.
    avatar_uri = avatar_ref = thumb_ref = None
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        appearance = _blueprint_json(zf, "persona_appearance.json")
        avatar_uri, avatar_ref, thumb_ref = _embedded_avatar(zf, set(zf.namelist()), appearance)
    except zipfile.BadZipFile:
        pass  # inspect() already validated; treat any re-read failure as no avatar

    snapshot: dict[str, Any] = {"shared": False, "imported": True, "capabilities": preview["capabilities"]}
    if avatar_uri:
        snapshot["avatar_data_uri"] = avatar_uri

    project_id = "hpersona-" + utcnow().strftime("%Y%m%d%H%M%S")
    link = HomePilotAgentLink(
        workspace_id=workspace_id,
        connection_id=LOCAL_CONNECTION_ID,
        account_ref=LOCAL_ACCOUNT_REF,
        homepilot_project_id=project_id,
        homepilot_model_id=f"persona:{project_id}",
        name=preview["name"],
        role=preview["role"],
        description=preview["description"],
        capabilities_json=preview["capabilities"],
        avatar_ref=avatar_ref,
        thumbnail_ref=thumb_ref,
        source_version=str(report["manifest"].get("source_homepilot_version") or ""),
        enabled=False,          # disabled until the user enables it, like a sync
        status="offline",       # imported offline — not chat-capable until a live HomePilot
        snapshot_json=snapshot,
        last_synced_at=utcnow(),
    )
    session.add(link)
    session.flush()
    return {"code": "imported", "agentId": link.id, "name": preview["name"]}
