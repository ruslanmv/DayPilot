"""Bridge to packages/presentation-engine (Node). One JSON request per process, no shell, bounded."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
ENGINE = Path(os.getenv("DAYPILOT_PRESENTATION_ENGINE", ROOT / "packages/presentation-engine/bin/build.mjs"))
TIMEOUT = 120


class EngineError(Exception):
    """Bad input (``problems`` lists them) or an engine failure."""

    def __init__(self, message: str, problems: list[str] | None = None, internal: bool = False) -> None:
        super().__init__(message)
        self.problems = problems or []
        self.internal = internal


def available() -> bool:
    return bool(shutil.which("node")) and ENGINE.exists()


def call(request: dict[str, Any], timeout: int = TIMEOUT) -> dict[str, Any]:
    if not available():
        raise EngineError("The presentation engine is not installed (needs Node 22 and packages/presentation-engine).", internal=True)
    # A minimal environment: the engine never needs credentials, proxies or the caller's variables.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp", "NODE_ENV": "production"}
    try:
        proc = subprocess.run(
            ["node", str(ENGINE)], input=json.dumps(request).encode(), capture_output=True,
            timeout=timeout, env=env, cwd=str(ENGINE.parent.parent), check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("The presentation engine took too long.", internal=True) from exc
    try:
        reply = json.loads(proc.stdout.decode() or "{}")
    except ValueError as exc:
        raise EngineError("The presentation engine returned an unreadable reply.", internal=True) from exc
    if proc.returncode == 2:
        raise EngineError(reply.get("error", "invalid input"), reply.get("problems"))
    if proc.returncode != 0:
        raise EngineError(reply.get("error", "engine failure")[:300], internal=True)
    return reply
