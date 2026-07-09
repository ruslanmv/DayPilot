from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAFE_INSTALL_STATE = "INSTALLED_DISABLED"
REQUIRED_ENTRIES = {
    "manifest.json",
    "blueprint/persona_agent.json",
    "preview/card.json",
}


@dataclass
class HomePilotPersonaPreview:
    kind: str
    schema_version: int
    package_version: int
    persona_id: str
    name: str
    role: str
    tools: list[str]
    content_rating: str
    has_avatar: bool
    safe_install_state: str = SAFE_INSTALL_STATE

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _read_json(pkg: zipfile.ZipFile, name: str, default: Any | None = None) -> Any:
    if name not in pkg.namelist():
        if default is not None:
            return default
        raise ValueError(f"Missing required entry: {name}")
    return json.loads(pkg.read(name).decode("utf-8"))


def preview_hpersona_bytes(data: bytes) -> dict[str, Any]:
    """Preview a HomePilot .hpersona package without installing it.

    DayPilot treats imported personas as untrusted. This function only reads the
    package manifest, blueprint, preview card, and dependency manifests. It does
    not execute code from the package.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as pkg:
        entries = set(pkg.namelist())
        missing = sorted(REQUIRED_ENTRIES - entries)
        if missing:
            raise ValueError(f"Invalid .hpersona package; missing: {missing}")

        manifest = _read_json(pkg, "manifest.json")
        agent = _read_json(pkg, "blueprint/persona_agent.json")
        card = _read_json(pkg, "preview/card.json")
        tools = _read_json(pkg, "dependencies/tools.json", default={})
        mcp_servers = _read_json(pkg, "dependencies/mcp_servers.json", default={})
        models = _read_json(pkg, "dependencies/models.json", default={})

        preview = HomePilotPersonaPreview(
            kind=manifest.get("kind", "unknown"),
            schema_version=int(manifest.get("schema_version", 0)),
            package_version=int(manifest.get("package_version", 0)),
            persona_id=agent.get("id") or card.get("name", "persona").lower().replace(" ", "_"),
            name=card.get("name") or agent.get("label") or "Unnamed Persona",
            role=card.get("role") or agent.get("role") or "Imported Persona",
            tools=list(agent.get("allowed_tools") or card.get("tools") or []),
            content_rating=manifest.get("content_rating", "unknown"),
            has_avatar=bool(manifest.get("contents", {}).get("has_avatar", False)),
        )

        return {
            **preview.model_dump(),
            "dependencies": {
                "tools": tools,
                "mcp_servers": mcp_servers,
                "models": models,
            },
            "policy": build_daypilot_policy(preview.model_dump()),
        }


def preview_hpersona_file(path: str | Path) -> dict[str, Any]:
    return preview_hpersona_bytes(Path(path).read_bytes())


def build_daypilot_policy(preview: dict[str, Any]) -> dict[str, Any]:
    """Create a safe DayPilot policy from HomePilot persona metadata."""
    allowed_tools = preview.get("tools", [])
    mapped_tools = []
    for tool in allowed_tools:
        mapped_tools.append({
            "homepilot_tool": tool,
            "daypilot_namespace": f"daypilot.homepilot.{tool}",
            "write_enabled": False,
            "requires_approval": True,
        })
    return {
        "install_state": SAFE_INSTALL_STATE,
        "source": "homepilot.hpersona",
        "persona_id": preview.get("persona_id"),
        "default_write_enabled": False,
        "require_human_approval": True,
        "mapped_tools": mapped_tools,
        "blocked_actions": [
            "send_email",
            "delete_email",
            "create_calendar_event",
            "send_message",
            "place_call",
            "execute_shell",
            "write_repository",
        ],
    }


def install_hpersona(path: str | Path, destination_root: str | Path = "local_data/installed_personas") -> dict[str, Any]:
    """Install a .hpersona into DayPilot local storage in disabled state."""
    src = Path(path)
    preview = preview_hpersona_file(src)
    persona_id = preview["persona_id"]
    dest = Path(destination_root) / persona_id
    dest.mkdir(parents=True, exist_ok=True)

    (dest / "persona.json").write_text(json.dumps(preview, indent=2), encoding="utf-8")
    (dest / "policy.json").write_text(json.dumps(preview["policy"], indent=2), encoding="utf-8")
    (dest / "dependencies.json").write_text(json.dumps(preview["dependencies"], indent=2), encoding="utf-8")
    shutil.copyfile(src, dest / src.name)

    return {"ok": True, "installed_at": str(dest), "persona": preview}
