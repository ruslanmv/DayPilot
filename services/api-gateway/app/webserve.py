"""Single-origin production serving.

In development the Vite dev server proxies `/api/*` to this gateway. In
production we don't want to run two servers or configure a reverse proxy just to
try DayPilot — so the gateway can serve the built web app itself:

  * an `/api` prefix-strip so the browser's same-origin `/api/...` calls reach
    the real routes (`/api/v1/...` → `/v1/...`, `/api/health` → `/health`),
    mirroring exactly what the dev proxy does; and
  * the compiled SPA mounted at `/` when a build is present.

Result: `uvicorn app.main:app` on one port serves the whole product. This is
opt-in by build presence, so tests and the dev flow are unaffected.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send


class ApiPrefixStripMiddleware:
    """Strip a leading `/api` so same-origin frontend calls reach the API,
    identical to the dev server's proxy rewrite. A no-op for every other path,
    so direct `/v1/...` and `/health` requests (tests, internal callers) are
    untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[4:] or "/"
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)) and (raw == b"/api" or raw.startswith(b"/api/")):
                    scope["raw_path"] = raw[4:] or b"/"
        await self.app(scope, receive, send)


def _web_dist() -> Path | None:
    """Locate the built operator-web (env override, else the repo default)."""
    override = os.getenv("DAYPILOT_WEB_DIST")
    if override:
        p = Path(override)
        return p if (p / "index.html").exists() else None
    # services/api-gateway/app/webserve.py -> repo root is parents[3].
    root = Path(__file__).resolve().parents[3]
    dist = root / "apps" / "operator-web" / "dist"
    return dist if (dist / "index.html").exists() else None


def mount_web(app: FastAPI) -> str:
    """Wire same-origin serving. Returns a short status string for logging."""
    app.add_middleware(ApiPrefixStripMiddleware)
    dist = _web_dist()
    if dist is None:
        return "api-only"
    # Mounted last (after routers) so API routes always win; html=True serves
    # index.html at `/` and static assets under it.
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
    return f"serving web from {dist}"
