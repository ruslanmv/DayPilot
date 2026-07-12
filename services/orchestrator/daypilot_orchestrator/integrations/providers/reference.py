"""Reference integration provider (batch I0/I1).

A built-in, offline provider that exercises the full integration loop — connect,
one read capability, one write capability, health — without any external
service. Used to prove the Phase-1 completion criteria and in CI.

Connect with credentials ``{"token": "fail"}`` to simulate an auth failure so the
"detect and display connection failure" path can be tested.
"""
from __future__ import annotations

from typing import Any

from ..provider import (
    AuthType,
    Capability,
    CapabilityKind,
    ConnectionStatus,
    IntegrationError,
    IntegrationHealth,
)

CAPABILITIES = [
    Capability("echo.read", CapabilityKind.READ, "Echo input back (read-only)."),
    Capability("echo.write", CapabilityKind.WRITE, "Record input (write; approval-gated)."),
]


class ReferenceProvider:
    provider = "reference"
    auth_type = AuthType.API_KEY

    def __init__(self) -> None:
        self._connected = False
        self._token: str | None = None

    def connect(self, credentials: dict[str, Any]) -> None:
        token = str(credentials.get("token", ""))
        if not token:
            raise IntegrationError("missing credential: token")
        if token == "fail":
            raise IntegrationError("authentication failed")
        self._token = token
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False
        self._token = None

    def list_capabilities(self) -> list[Capability]:
        return list(CAPABILITIES)

    def execute(self, action: str, payload: Any) -> Any:
        if not self._connected:
            raise IntegrationError("not connected")
        if action == "echo.read":
            return {"echo": payload}
        if action == "echo.write":
            return {"written": payload, "ok": True}
        raise IntegrationError(f"unknown action '{action}'")

    def get_health(self) -> IntegrationHealth:
        if self._connected:
            return IntegrationHealth(ConnectionStatus.CONNECTED, "ok", latency_ms=1.0)
        return IntegrationHealth(ConnectionStatus.ERROR, "not connected")


def _factory() -> ReferenceProvider:
    return ReferenceProvider()


# Registered on import (see registry.py).
from ..registry import register_provider  # noqa: E402

register_provider("reference", _factory)
