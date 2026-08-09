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
    Capability("chat.history", CapabilityKind.READ, "Read recent root messages in a channel."),
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
        if action == "chat.history":
            # Root messages only — a standup reminder is a root message, and its
            # replies are other people's updates. Structured (not flattened to
            # text) because thread resolution matches on bot identity and ts,
            # not only on the wording.
            params: dict[str, Any] = {
                "channel": payload["channel"],
                "limit": int(payload.get("limit") or 50),
            }
            for key, slack_key in (("oldest", "oldest"), ("latest", "latest")):
                if payload.get(key):
                    params[slack_key] = str(payload[key])
            data = self._call("GET", "/conversations.history", params=params)
            return {"messages": [
                {
                    "ts": m.get("ts"),
                    "text": m.get("text", ""),
                    "botId": m.get("bot_id"),
                    "user": m.get("user"),
                    "subtype": m.get("subtype"),
                    "threadTs": m.get("thread_ts"),
                }
                for m in data.get("messages", [])
            ]}
        if action == "chat.send":
            # `threadTs` is what makes this a *reply*. Without it Slack posts a
            # new root message in the channel, which for a standup means shouting
            # into the channel instead of answering the reminder.
            body: dict[str, Any] = {"channel": payload["channel"], "text": payload["text"]}
            if payload.get("threadTs"):
                body["thread_ts"] = str(payload["threadTs"])
            # Slack dedupes retries of an identical (channel, text) pair only
            # within a short window, so the caller's own key is what actually
            # guarantees one reply per day. It rides along for the audit trail
            # and is echoed back so the caller can prove which send this was.
            client_message_id = payload.get("clientMessageId")
            data = self._call("POST", "/chat.postMessage", json=body)
            return {
                "ts": data.get("ts"),
                "channel": data.get("channel"),
                "threadTs": body.get("thread_ts"),
                "clientMessageId": client_message_id,
            }
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
