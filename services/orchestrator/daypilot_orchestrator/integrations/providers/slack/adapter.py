"""Slack provider adapter (batch I2/I3).

Implements the IntegrationProvider contract over the Slack Web API. Reads
(`chat.read`) run immediately; sends (`chat.send`) are classified WRITE, so the
gateway routes them through the Approval Center — nothing is ever posted without
a human approval. An httpx transport is injectable so the loop is unit-testable
without a live Slack workspace.
"""
from __future__ import annotations

from typing import Any

import httpx

from ...provider import (
    AuthType,
    Capability,
    CapabilityKind,
    ConnectionStatus,
    IntegrationError,
    IntegrationHealth,
)

SLACK_API = "https://slack.com/api"

CAPABILITIES = [
    Capability("chat.read", CapabilityKind.READ, "Read an authorized thread/conversation."),
    Capability("chat.send", CapabilityKind.WRITE, "Send a message (approval-gated)."),
]


class SlackProvider:
    provider = "slack"
    auth_type = AuthType.OAUTH

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._token: str | None = None
        self._transport = transport

    def _client(self) -> httpx.Client:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        return httpx.Client(base_url=SLACK_API, headers=headers, timeout=30.0, transport=self._transport)

    def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with self._client() as client:
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            data = response.json()
        if not data.get("ok", False):
            # Slack error codes are safe to surface; they carry no secrets.
            raise IntegrationError(f"slack: {data.get('error', 'unknown_error')}")
        return data

    def connect(self, credentials: dict[str, Any]) -> None:
        token = str(credentials.get("bot_token") or credentials.get("token") or "")
        if not token:
            raise IntegrationError("missing credential: bot_token")
        self._token = token
        try:
            self._call("POST", "/auth.test")  # verify the token
        except httpx.HTTPError as exc:
            self._token = None
            raise IntegrationError("slack unreachable") from exc

    def disconnect(self) -> None:
        self._token = None

    def list_capabilities(self) -> list[Capability]:
        return list(CAPABILITIES)

    def execute(self, action: str, payload: Any) -> Any:
        if not self._token:
            raise IntegrationError("not connected")
        payload = payload or {}
        if action == "chat.read":
            data = self._call("GET", "/conversations.replies",
                              params={"channel": payload["channel"], "ts": payload["ts"]})
            return {"messages": [m.get("text", "") for m in data.get("messages", [])]}
        if action == "chat.send":
            data = self._call("POST", "/chat.postMessage",
                              json={"channel": payload["channel"], "text": payload["text"]})
            return {"ts": data.get("ts"), "channel": data.get("channel")}
        raise IntegrationError(f"unknown action '{action}'")

    def get_health(self) -> IntegrationHealth:
        if not self._token:
            return IntegrationHealth(ConnectionStatus.ERROR, "not connected")
        try:
            self._call("POST", "/auth.test")
            return IntegrationHealth(ConnectionStatus.CONNECTED, "ok")
        except (IntegrationError, httpx.HTTPError) as exc:
            return IntegrationHealth(ConnectionStatus.ERROR, str(exc))


def _factory() -> SlackProvider:
    return SlackProvider()


from ...registry import register_provider  # noqa: E402

register_provider("slack", _factory)
