"""Content-addressed artifact store on local disk. Keys never come from clients; files are immutable."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

KINDS = {"pptx": ".pptx", "pdf": ".pdf", "png": ".png"}


def root() -> Path:
    base = Path(os.getenv("DAYPILOT_PRESENTATIONS_DIR", "local_data/presentations"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def put(workspace_id: str, kind: str, data: bytes) -> tuple[str, str]:
    """Write once; returns (sha256, store_key). Re-writing the same bytes is a no-op."""
    digest = hashlib.sha256(data).hexdigest()
    space = hashlib.sha256(workspace_id.encode()).hexdigest()[:16]
    key = f"{space}/{digest}{KINDS[kind]}"
    path = root() / key
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    return digest, key


def get(key: str) -> bytes:
    path = (root() / key).resolve()
    if root().resolve() not in path.parents:
        raise FileNotFoundError(key)
    return path.read_bytes()
