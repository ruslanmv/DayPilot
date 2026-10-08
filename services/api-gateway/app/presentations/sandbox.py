"""Run an expert JavaScript builder in isolation.

Layers, all required (the code refuses to run when any is missing):
1. An unprivileged user (nobody) with no-new-privileges and no supplementary groups.
2. A fresh user + network namespace: no network interfaces except a down loopback.
3. Node's permission model: read only the engine, its dependencies and this run's input folder;
   write only this run's output folder; no child processes, workers, WASI or native addons.
4. Resource limits: CPU seconds, processes, open files, output file size, heap; a wall-clock timeout.
5. An empty environment: no credentials, tokens or proxy settings reach the builder.

The static pre-check below gives early, readable feedback; it is not the security boundary.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .engine import ENGINE

ENGINE_DIR = ENGINE.parent.parent
EXPERT = ENGINE_DIR / "bin" / "expert.mjs"
MAX_SCRIPT = 200_000
TIMEOUT = 60
NOBODY = 65534
DENY = [
    (r"^\s*import\s|\bimport\s*\(", "imports (everything you need is on the `deck` argument)"),
    (r"\brequire\s*\(", "require()"),
    (r"\bprocess\b", "process"),
    (r"\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(", "eval / Function"),
    (r"\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b", "network access"),
    (r"\bchild_process\b|\bWorker\b|\bWebAssembly\b", "processes, workers or WebAssembly"),
    (r"\bglobalThis\b|\b__proto__\b", "globalThis / __proto__"),
]


class SandboxError(Exception):
    pass


def available() -> dict[str, Any]:
    tools = {t: bool(shutil.which(t)) for t in ("node", "setpriv", "unshare", "prlimit")}
    ok = all(tools.values()) and EXPERT.exists()
    if ok:
        try:
            probe = subprocess.run(["setpriv", f"--reuid={NOBODY}", f"--regid={NOBODY}", "--clear-groups", "--no-new-privs", "unshare", "-rn", "--", "true"], capture_output=True, timeout=10)
            ok = probe.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
    return {"ready": ok, **tools}


_STRINGS = re.compile(r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"", re.S)


def precheck(script: str) -> list[str]:
    """Plain words inside quoted strings and comments ("our process") are fine; code is not."""
    problems = []
    code = _STRINGS.sub("''", script)
    if len(script.encode()) > MAX_SCRIPT:
        problems.append("The builder is larger than 200 KB.")
    if not re.search(r"\bexport\s+default\b", script):
        problems.append("The builder must `export default` a function that receives `deck`.")
    for pattern, label in DENY:
        if re.search(pattern, code, re.M):
            problems.append(f"Not allowed in builders: {label}.")
    return problems


def _readable_roots() -> list[str]:
    """The engine and the real folders its dependencies resolve to (pnpm keeps them outside)."""
    roots = {str(ENGINE_DIR.resolve())}
    for dep in ("pptxgenjs", "jszip"):
        link = ENGINE_DIR / "node_modules" / dep
        if link.exists():
            real = link.resolve()
            # .../node_modules/.pnpm/<pkg@ver>/node_modules/<pkg>: allow the whole pnpm store folder
            parts = real.parts
            if ".pnpm" in parts:
                roots.add(str(Path(*parts[: parts.index(".pnpm") + 1])))
            else:
                roots.add(str(real))
    return sorted(roots)


def run(script: str, kit: dict[str, Any], assets: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Build the deck in the sandbox. Returns (pptx bytes, engine reply). Raises SandboxError."""
    status = available()
    if not status["ready"]:
        raise SandboxError("Expert builds are unavailable on this server: the sandbox (setpriv, unshare, prlimit, node) is missing.")
    problems = precheck(script)
    if problems:
        raise SandboxError(" ".join(problems))
    node = shutil.which("node")
    with tempfile.TemporaryDirectory(prefix="dp-expert-") as tmp:
        work = Path(tmp)
        os.chmod(work, 0o755)
        inp, out = work / "in", work / "out"
        inp.mkdir()
        out.mkdir()
        (inp / "script.mjs").write_text(script, encoding="utf-8")
        (inp / "kit.json").write_text(json.dumps(kit), encoding="utf-8")
        (inp / "assets.json").write_text(json.dumps(assets), encoding="utf-8")
        for f in inp.iterdir():
            os.chmod(f, 0o644)
        os.chmod(inp, 0o555)
        os.chown(out, NOBODY, NOBODY)
        os.chmod(out, 0o700)
        result = out / "deck.pptx"
        cmd = [
            "setpriv", f"--reuid={NOBODY}", f"--regid={NOBODY}", "--clear-groups", "--no-new-privs",
            "unshare", "-rn", "--",
            "prlimit", "--cpu=60", "--nproc=64", "--nofile=256", f"--fsize={150 * 1024 * 1024}", "--",
            node, "--max-old-space-size=512", "--experimental-permission",
            *[f"--allow-fs-read={r}" for r in (*_readable_roots(), str(inp))], f"--allow-fs-write={out}",
            "--disable-warning=ExperimentalWarning", str(EXPERT), str(inp), str(result),
        ]
        env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "NODE_ENV": "production"}
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, env=env, cwd=str(work), check=False)
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"The builder ran longer than {TIMEOUT} seconds and was stopped.") from exc
        try:
            reply = json.loads(proc.stdout.decode() or "{}")
        except ValueError:
            reply = {}
        if proc.returncode != 0 or not result.exists():
            lines = [x for x in proc.stderr.decode(errors="replace").splitlines() if x.strip() and not x.startswith(("Node.js v", "    at "))]
            errors = [x for x in lines if re.match(r"^\w*Error\b|^\w+Error:", x.strip())]
            message = reply.get("error") or (errors or lines or ["the builder stopped unexpectedly"])[-1].strip()
            raise SandboxError(message[:400])
        data = result.read_bytes()
    return data, reply
