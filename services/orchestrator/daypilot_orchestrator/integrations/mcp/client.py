"""MCP client transports (batch I4).

Two transports, both behind one interface so the rest of DayPilot never cares
which is used: Streamable HTTP (remote servers) and STDIO (local servers). Both
are constructed with injectable primitives so the tool router is unit-testable
without a live MCP server. Tool calls always go through the DayPilot policy +
approval layer first — a client is never handed to the model directly.
"""
from __future__ import annotations

from typing import Any, Protocol

import httpx

DEFAULT_TIMEOUT = 30.0


class MCPClientError(RuntimeError):
    pass


class MCPClient(Protocol):
    def list_tools(self) -> list[dict[str, Any]]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class StreamableHttpClient:
    """Remote MCP server over Streamable HTTP. Uses a compact request contract
    (`tools/list`, `tools/call`); an httpx transport is injectable for tests."""

    def __init__(self, endpoint: str, transport: httpx.BaseTransport | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.endpoint = endpoint
        self._transport = transport
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.endpoint, timeout=self._timeout, transport=self._transport)

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.post("", json={"method": method, "params": params})
            response.raise_for_status()
            data = response.json()
        if "error" in data and data["error"]:
            raise MCPClientError(str(data["error"]))
        return data.get("result", data)

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._rpc("tools/list", {}).get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


class StdioClient:
    """Local MCP server launched over STDIO. The command runner is injectable so
    tests need no subprocess; production wires it to an MCP stdio session."""

    def __init__(self, command: str, runner: Any | None = None) -> None:
        self.command = command
        self._runner = runner  # callable(method, params) -> dict

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._runner is None:  # pragma: no cover - requires a live stdio session
            raise MCPClientError("stdio runner not configured")
        return self._runner(method, params)

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._call("tools/list", {}).get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call("tools/call", {"name": name, "arguments": arguments})
