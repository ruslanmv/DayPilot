"""Local copies of agent portraits, so the Agents directory never goes blank.

Portraits live in HomePilot and are proxied by the gateway. That made every
card depend on a live, correctly configured connection: when HomePilot was
down, restarting, or the saved connection had lost its address (credentials
were process-local before they were persisted), every portrait answered 404
and the whole directory fell back to initials at once.

Each portrait the gateway fetches successfully is now kept here, and a sync
fetches the ones that are missing or changed. When HomePilot can't be asked,
the last good copy is served instead. Only real image bytes (PNG, JPEG, WebP,
GIF, checked by signature rather than by the declared type) are stored, each
under a hashed name in an owner-only directory, written atomically.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

MAX_BYTES = 2_000_000


def _root() -> Path:
    return Path(os.getenv("DAYPILOT_AGENT_PORTRAITS_DIR", "local_data/agent-portraits"))


def image_type(content: bytes) -> str | None:
    """The image type from the file signature, or None for anything else."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def _key(workspace_id: str, link_id: str) -> str:
    return hashlib.sha256(f"{workspace_id}\0{link_id}".encode()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".portrait-")
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save(workspace_id: str, link_id: str, ref: str, content: bytes) -> bool:
    """Keep a copy of the portrait fetched for ``ref``. Returns whether it was stored."""
    kind = image_type(content)
    if kind is None or not content or len(content) > MAX_BYTES:
        return False
    key = _key(workspace_id, link_id)
    meta = {"ref": ref, "type": kind, "sha256": hashlib.sha256(content).hexdigest(), "saved_at": time.time()}
    try:
        current = _meta(key)
        if current.get("sha256") == meta["sha256"] and current.get("ref") == ref:
            return True
        _write(_root() / f"{key}.img", content)
        _write(_root() / f"{key}.json", json.dumps(meta).encode())
    except OSError:
        return False
    return True


def _meta(key: str) -> dict[str, Any]:
    try:
        return json.loads((_root() / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def has(workspace_id: str, link_id: str, ref: str | None) -> bool:
    """Whether the stored copy is the portrait ``ref`` currently points at."""
    return bool(ref) and _meta(_key(workspace_id, link_id)).get("ref") == ref


def load(workspace_id: str, link_id: str) -> tuple[bytes, str] | None:
    """The last good copy, re-checked to be an image, or None."""
    key = _key(workspace_id, link_id)
    try:
        content = (_root() / f"{key}.img").read_bytes()
    except OSError:
        return None
    kind = image_type(content)
    return (content, kind) if kind else None


def forget(workspace_id: str, link_id: str) -> None:
    key = _key(workspace_id, link_id)
    for suffix in (".img", ".json"):
        (_root() / f"{key}{suffix}").unlink(missing_ok=True)
