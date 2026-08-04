"""Ollabridge connector — DayPilot's default LLM provider layer (batch B5).

Ollabridge exposes one OpenAI-compatible endpoint that routes to local Ollama,
remote GPUs, and cloud accounts. DayPilot talks to that single URL + key and
lets Ollabridge decide where each request runs.

Security: prompts and API keys are never logged. Errors carry only status and
request context, never message bodies or credentials.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_TIMEOUT = 60.0


def normalize_gateway_root(url: str) -> str:
    """Return the gateway *root* for an Ollabridge base URL.

    Ollabridge's health/pairing routes live at the root (``/health``,
    ``/device/*``) while the OpenAI-compatible surface lives under ``/v1``
    (``/v1/models``, ``/v1/chat/completions``). Callers hand us the base URL in
    whatever shape they have it — sometimes the bare root, sometimes the OpenAI
    base already ending in ``/v1`` (that's what DayPilot shows the user), and the
    cloud sometimes uses the ``/ollama/v1`` alias. We normalise every form to the
    root so method paths append cleanly and never double up (the bug that made a
    healthy local gateway look offline: ``…/v1`` + ``/v1/models`` → ``/v1/v1/models``).
    """
    u = (url or "").strip().rstrip("/")
    for suffix in ("/ollama/v1", "/v1"):
        if u.endswith(suffix):
            return u[: -len(suffix)]
    return u


@dataclass
class OllabridgeConnector:
    base_url: str
    api_key: str | None = None
    model: str = "llama3.1"
    name: str = "ollabridge"
    # Deployment target. Both are the same OpenAI-compatible consumer surface
    # (Bearer key + /v1/chat/completions); "cloud" additionally supports the
    # TV-style device-pairing handshake. DayPilot pairs with either.
    mode: str = "local"  # "local" | "cloud"
    timeout: float = DEFAULT_TIMEOUT
    # Injectable for tests; defaults to a real client per call.
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Store the canonical gateway root so /v1/* and /health resolve without
        # doubling, regardless of the shape the caller passed in.
        self.base_url = normalize_gateway_root(self.base_url)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        # Ollabridge accepts the key as a Bearer token or as X-API-Key. The
        # local gateway's local-trust mode honours either; the cloud validates
        # the Bearer JWT. Sending both for local matches the documented contract.
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.mode == "local":
            headers["X-API-Key"] = self.api_key
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
            transport=self.transport,
        )

    def generate(self, prompt: str, task: str = "general", model: str | None = None) -> dict:
        return self.generate_messages(
            [{"role": "user", "content": prompt}], task=task, model=model
        )

    def generate_messages(
        self,
        messages: list[dict[str, str]],
        task: str = "general",
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict:
        """Run a full chat (system + history + user) through the provider's
        OpenAI-compatible ``/v1/chat/completions``. Raises on transport/HTTP error
        so the caller can fall back rather than fabricate an answer."""
        payload = {
            "model": model or self.model,
            "messages": list(messages),
            "temperature": temperature,
        }
        with self._client() as client:
            response = client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return {
            "backend": self.name,
            "task": task,
            "model": payload["model"],
            "text": text,
            "usage": usage,
        }

    def list_models(self) -> list[str]:
        with self._client() as client:
            response = client.get("/v1/models")
            response.raise_for_status()
            data = response.json()
        return [m.get("id") for m in data.get("data", []) if m.get("id")]

    def health(self) -> bool:
        """Liveness check against the gateway's root ``/health`` endpoint.

        ``/health`` is unauthenticated on both local and cloud, so this answers
        "is a gateway listening here?" independently of whether a key is valid or
        any model is loaded. Never raises.
        """
        try:
            with self._client() as client:
                response = client.get("/health")
            return response.status_code < 500
        except (httpx.HTTPError, ValueError):
            return False

    def ping(self) -> tuple[bool, float | None, list[str]]:
        """Return (reachable, latency_ms, models). Never raises."""
        start = time.perf_counter()
        try:
            models = self.list_models()
        except (httpx.HTTPError, ValueError):
            return False, None, []
        latency_ms = (time.perf_counter() - start) * 1000
        return True, round(latency_ms, 1), models

    # --- Cloud device pairing (TV-style ABCD-1234 codes) --------------------
    # Only meaningful against an Ollabridge Cloud endpoint. The local gateway
    # uses a key printed at startup and does not need pairing.
    def start_pairing(self) -> dict:
        """Begin cloud device pairing.

        Returns the cloud's session payload (user_code, device_code,
        verification_uri, interval). Raises on transport/HTTP error.
        """
        with self._client() as client:
            response = client.post("/device/start")
            response.raise_for_status()
            return response.json()

    def poll_pairing(self, device_code: str) -> dict:
        """Poll for approval of a pairing session.

        Returns the cloud payload, typically {"status": "pending"} until the
        user approves, then {"status": "approved", "api_key": "ob_live_..."}.
        """
        with self._client() as client:
            response = client.post("/device/poll", json={"device_code": device_code})
            response.raise_for_status()
            return response.json()


# Sensible defaults for each deployment target. Both are OpenAI-compatible.
# The cloud host is the *live* OllaBridge Cloud space (ruslanmv-ollabridge.hf.space):
# its /health, /login, /register and POST /v1/auth/login are all deployed. The
# ``…-cloud.hf.space`` name is not served (404s), so it must not be the default.
LOCAL_DEFAULT_URL = "http://localhost:11435/v1"
CLOUD_DEFAULT_URL = "https://ruslanmv-ollabridge.hf.space/v1"


def connector_from_env(transport: httpx.BaseTransport | None = None) -> OllabridgeConnector:
    """Build a connector for either the local gateway or Ollabridge Cloud.

    Selection: ``OLLABRIDGE_MODE`` (``local`` default, or ``cloud``) picks the
    default endpoint; an explicit ``OLLABRIDGE_URL`` / ``OLLABRIDGE_BASE_URL``
    always wins. The API key is a Bearer token in both modes (``sk-ollabridge-``
    locally, ``ob_live_``/``ob_test_`` in the cloud).
    """
    mode = os.getenv("OLLABRIDGE_MODE", "local").strip().lower()
    if mode not in ("local", "cloud"):
        mode = "local"
    default_url = CLOUD_DEFAULT_URL if mode == "cloud" else LOCAL_DEFAULT_URL
    raw_url = os.getenv("OLLABRIDGE_URL") or os.getenv("OLLABRIDGE_BASE_URL") or default_url
    return OllabridgeConnector(
        base_url=raw_url.removesuffix("/v1"),
        api_key=os.getenv("OLLABRIDGE_API_KEY") or None,
        model=os.getenv("OLLABRIDGE_DEFAULT_MODEL") or os.getenv("OLLABRIDGE_MODEL", "llama3.1"),
        mode=mode,
        transport=transport,
    )
