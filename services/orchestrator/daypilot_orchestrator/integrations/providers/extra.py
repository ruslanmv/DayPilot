"""Additional providers behind the one interface (batch I7).

GitHub and Google Calendar, implemented against IntegrationProvider with the same
capability classification and injectable transports as Slack. Adding a provider
is a self-contained adapter — no new approval, notification, or gateway logic —
which is the whole point of Phase 4.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..provider import (
    AuthType,
    Capability,
    CapabilityKind,
    ConnectionStatus,
    IntegrationError,
    IntegrationHealth,
)
from ..registry import register_provider

GITHUB_API = "https://api.github.com"
GOOGLE_CAL_API = "https://www.googleapis.com/calendar/v3"


class _BearerProvider:
    """Shared plumbing for OAuth Bearer providers with an injectable transport."""

    provider = "base"
    auth_type = AuthType.OAUTH
    base_url = ""
    _cred_keys = ("token", "access_token")

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._token: str | None = None
        self._transport = transport

    def _client(self) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0, transport=self._transport)

    def _verify_path(self) -> str:
        return "/"

    def connect(self, credentials: dict[str, Any]) -> None:
        token = next((str(credentials[k]) for k in self._cred_keys if credentials.get(k)), "")
        if not token:
            raise IntegrationError(f"missing credential: {self._cred_keys[0]}")
        self._token = token
        try:
            with self._client() as client:
                resp = client.get(self._verify_path())
            if resp.status_code >= 400:
                raise IntegrationError(f"{self.provider} auth failed")
        except httpx.HTTPError as exc:
            self._token = None
            raise IntegrationError(f"{self.provider} unreachable") from exc

    def disconnect(self) -> None:
        self._token = None

    def get_health(self) -> IntegrationHealth:
        if not self._token:
            return IntegrationHealth(ConnectionStatus.ERROR, "not connected")
        try:
            with self._client() as client:
                ok = client.get(self._verify_path()).status_code < 400
            return IntegrationHealth(ConnectionStatus.CONNECTED if ok else ConnectionStatus.ERROR,
                                     "ok" if ok else "auth failed")
        except httpx.HTTPError as exc:
            return IntegrationHealth(ConnectionStatus.ERROR, str(exc))


class GitHubProvider(_BearerProvider):
    provider = "github"
    base_url = GITHUB_API

    def _verify_path(self) -> str:
        return "/user"

    def list_capabilities(self) -> list[Capability]:
        return [
            Capability("repo.read", CapabilityKind.READ, "Read repository metadata."),
            Capability("checks.read", CapabilityKind.READ, "Read commit check runs."),
            Capability("pr.create", CapabilityKind.WRITE, "Open a pull request (approval-gated)."),
        ]

    def execute(self, action: str, payload: Any) -> Any:
        if not self._token:
            raise IntegrationError("not connected")
        payload = payload or {}
        with self._client() as client:
            if action == "repo.read":
                r = client.get(f"/repos/{payload['repo']}")
            elif action == "checks.read":
                r = client.get(f"/repos/{payload['repo']}/commits/{payload.get('ref', 'main')}/check-runs")
            elif action == "pr.create":
                r = client.post(f"/repos/{payload['repo']}/pulls", json={
                    "title": payload["title"], "head": payload["head"], "base": payload.get("base", "main"),
                })
            else:
                raise IntegrationError(f"unknown action '{action}'")
            r.raise_for_status()
            return r.json()


class GoogleCalendarProvider(_BearerProvider):
    provider = "calendar"
    base_url = GOOGLE_CAL_API

    def _verify_path(self) -> str:
        return "/users/me/calendarList"

    def list_capabilities(self) -> list[Capability]:
        return [
            Capability("events.read", CapabilityKind.READ, "Read calendar events."),
            Capability("events.write", CapabilityKind.WRITE, "Create/move events (approval-gated)."),
        ]

    def execute(self, action: str, payload: Any) -> Any:
        if not self._token:
            raise IntegrationError("not connected")
        payload = payload or {}
        cal = payload.get("calendarId", "primary")
        with self._client() as client:
            if action == "events.read":
                r = client.get(f"/calendars/{cal}/events")
            elif action == "events.write":
                r = client.post(f"/calendars/{cal}/events", json=payload.get("event", {}))
            else:
                raise IntegrationError(f"unknown action '{action}'")
            r.raise_for_status()
            return r.json()


register_provider("github", lambda: GitHubProvider())
register_provider("calendar", lambda: GoogleCalendarProvider())
