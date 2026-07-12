"""Integration provider contract (batch I0).

Every integration — native API or MCP — is exposed to DayPilot through this one
interface, so the core never learns which transport a provider uses internally.
Capabilities are classified so the platform can apply the default permission
model (reads run immediately, writes/destructive actions require approval).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class CapabilityKind(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    ERROR = "error"
    EXPIRED = "expired"


class AuthType(str, Enum):
    OAUTH = "oauth"
    API_KEY = "api_key"
    MCP = "mcp"


@dataclass(frozen=True)
class Capability:
    id: str  # e.g. "echo.read", "customer.update"
    kind: CapabilityKind
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind.value, "description": self.description}


@dataclass(frozen=True)
class IntegrationHealth:
    status: ConnectionStatus
    detail: str = ""
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "detail": self.detail, "latencyMs": self.latency_ms}


class IntegrationError(RuntimeError):
    """Raised by a provider on connect/execute failure (never leaks secrets)."""


class CapabilityNotFound(KeyError):
    pass


@runtime_checkable
class IntegrationProvider(Protocol):
    """The minimum interface. Mirrors the TypeScript `IntegrationProvider`.

    DayPilot's gateway supplies credentials to `connect`; providers must not read
    secrets from anywhere else.
    """

    provider: str
    auth_type: AuthType

    def connect(self, credentials: dict[str, Any]) -> None: ...
    def disconnect(self) -> None: ...
    def list_capabilities(self) -> list[Capability]: ...
    def execute(self, action: str, payload: Any) -> Any: ...
    def get_health(self) -> IntegrationHealth: ...
