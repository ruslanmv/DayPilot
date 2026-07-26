"""HTTP client for a side-by-side HomePilot install.

DayPilot's backend is the ONLY thing that talks to HomePilot (rule 4 — the
browser never does). This client speaks HomePilot's existing REST + OpenAI-
compatible API: health, persona discovery (/projects, /v1/models), and chat
(/v1/chat/completions with ``persona:<project_id>``). The API key is presented as
both ``X-API-Key`` and ``Authorization: Bearer`` (HomePilot accepts either) and is
NEVER logged. Every method degrades gracefully; nothing here raises past the
caller for a transport error — it returns a structured result instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from .contracts import ToolMode

DEFAULT_TIMEOUT = 30.0


@dataclass
class HealthResult:
    reachable: bool
    status_code: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class HomePilotClient:
    """Thin, safe client. ``base_url`` should include HomePilot's ``/api`` prefix
    (e.g. ``http://homepilot:7860/api``)."""

    base_url: str
    api_key: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"X-Client-Type": "daypilot"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        if extra:
            headers.update(extra)
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url.rstrip("/"),
            headers=self._headers(),
            timeout=self.timeout,
            transport=self.transport,
        )

    # -- discovery -----------------------------------------------------------
    def health(self) -> HealthResult:
        """Liveness + identity probe against HomePilot's ``/health``. Never raises."""
        try:
            with self._client() as c:
                r = c.get("/health")
        except httpx.ConnectError:
            return HealthResult(reachable=False, error="connection_refused")
        except httpx.TimeoutException:
            return HealthResult(reachable=False, error="timeout")
        except httpx.HTTPError:
            return HealthResult(reachable=False, error="transport_error")
        if r.status_code in (401, 403):
            return HealthResult(reachable=True, status_code=r.status_code, error="unauthorized")
        try:
            payload = r.json() if "json" in r.headers.get("content-type", "") else {}
        except ValueError:
            payload = {}
        return HealthResult(reachable=r.status_code < 500, status_code=r.status_code, payload=payload)

    def list_projects(self) -> list[dict[str, Any]]:
        """Return HomePilot projects (unfiltered). Empty list on any failure."""
        try:
            with self._client() as c:
                r = c.get("/projects")
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            return []
        if isinstance(data, dict):
            projects = data.get("projects") or data.get("data") or []
        else:
            projects = data
        return [p for p in projects if isinstance(p, dict)]

    def list_models(self) -> list[str]:
        """Return model ids from HomePilot's OpenAI-compatible ``/v1/models``.

        Persona projects with the shared API enabled appear as
        ``persona:<project_id>``. Empty list on any failure.
        """
        try:
            with self._client() as c:
                r = c.get("/v1/models")
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]

    def capabilities(self) -> dict[str, Any] | None:
        """Optional bridge-capability advertisement (Phase 12). None if absent →
        DayPilot falls back to legacy chat-only mode."""
        try:
            with self._client() as c:
                r = c.get("/v1/integrations/daypilot/capabilities")
            if r.status_code != 200:
                return None
            return r.json()
        except (httpx.HTTPError, ValueError):
            return None

    def identity(self) -> dict[str, Any] | None:
        """Which HomePilot account this connection is bound to (multi-account
        security). Returns ``{account_ref, account_label, authenticated, scope}``
        or None if the endpoint is absent (older HomePilot) — the caller then
        derives a stable fingerprint from the credential so agents are still
        bound to *some* account and can't blend across a key change."""
        try:
            with self._client() as c:
                r = c.get("/v1/integrations/daypilot/identity")
            if r.status_code != 200:
                return None
            return r.json()
        except (httpx.HTTPError, ValueError):
            return None

    # -- chat ----------------------------------------------------------------
    def persona_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        tool_mode: ToolMode = ToolMode.PROPOSE,
        session_id: str | None = None,
        include_media: bool = True,
    ) -> dict[str, Any]:
        """Send a chat turn to a HomePilot persona in propose-only mode.

        Returns the raw OpenAI-compatible response dict (which may carry
        ``x_homepilot`` + ``x_directives`` for bridge-aware HomePilot). Raises
        httpx.HTTPError on transport/HTTP failure so the caller can surface a
        retryable error while preserving the user's message.
        """
        extra = {
            "X-HomePilot-Bridge-Version": "1",
            "X-HomePilot-Tool-Mode": tool_mode.value,
            "X-Include-Media": "true" if include_media else "false",
        }
        if session_id:
            extra["X-HomePilot-Session-ID"] = session_id
        payload = {"model": model, "messages": messages, "stream": False}
        with httpx.Client(
            base_url=self.base_url.rstrip("/"),
            headers=self._headers(extra),
            timeout=self.timeout,
            transport=self.transport,
        ) as c:
            r = c.post("/v1/chat/completions", json=payload)
            r.raise_for_status()
            return r.json()
