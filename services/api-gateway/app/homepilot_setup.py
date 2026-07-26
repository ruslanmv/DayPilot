"""HomePilot setup: auto-detection + connection diagnostics (backend-only).

The guided setup wizard needs to (a) find a HomePilot installation on this host
and (b) run a human-readable connection checklist against an address. Both happen
here, on the backend — the browser never probes the network (contract rule 4).

Security:
  * Detection only ever tries a fixed, code-owned candidate list.
  * A user-supplied address is passed through ``_ssrf_ok`` first: cloud-metadata
    and link-local addresses are always rejected. Loopback/private addresses are
    allowed (a local HomePilot is the common case), gated by the caller's
    ``allowPrivate`` intent for anything the user typed.
  * The API key is never echoed back to the caller and never logged.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

from daypilot_orchestrator.homepilot.client import HomePilotClient
from daypilot_orchestrator.homepilot.contracts import is_persona_model

# Fixed detection candidates (api_url, browser_url, installation_type). Ordered
# most-specific-first: the Docker service name, then host-gateway, then loopback.
# HomePilot's desktop / single-container build serves its UI + proxied API on
# 7860; its full compose stack serves the frontend on 3000 and the API on 8000.
DETECT_CANDIDATES: list[tuple[str, str, str]] = [
    ("http://homepilot:7860/api", "http://localhost:7860", "single_container"),
    ("http://host.docker.internal:7860/api", "http://localhost:7860", "desktop"),
    ("http://127.0.0.1:7860/api", "http://localhost:7860", "desktop"),
    ("http://localhost:7860/api", "http://localhost:7860", "desktop"),
    ("http://homepilot:8000", "http://localhost:3000", "docker_compose"),
    ("http://host.docker.internal:8000", "http://localhost:3000", "docker_compose"),
    ("http://127.0.0.1:8000", "http://localhost:3000", "docker_compose"),
]

# Never connect to these — cloud instance-metadata and link-local ranges. Blocked
# regardless of the allowPrivate intent (SSRF hardening).
_METADATA_HOSTS = {"169.254.169.254", "100.100.100.200", "metadata.google.internal", "metadata"}
_DETECT_TIMEOUT = 2.5
_TEST_TIMEOUT = 8.0


def _resolved_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    out: list[ipaddress._BaseAddress] = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return out


def _ssrf_ok(url: str, *, allow_private: bool = True) -> bool:
    """Whether a URL is safe to connect to. Always blocks cloud-metadata and
    link-local targets; blocks private/loopback only when ``allow_private`` is
    False (an advanced opt-in the wizard exposes for remote-only deployments)."""
    parts = urlsplit(url if "://" in (url or "") else f"http://{url}")
    host = (parts.hostname or "").lower()
    if not host or parts.scheme not in ("http", "https"):
        return False
    if host in _METADATA_HOSTS:
        return False
    # A literal IP host, plus any address the name resolves to, must clear the
    # metadata/link-local bar; private ranges are allowed unless opted out.
    candidates: list[ipaddress._BaseAddress] = []
    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        candidates.extend(_resolved_ips(host))
    for ip in candidates:
        if ip.is_link_local:  # 169.254.0.0/16, fe80::/10 — includes metadata
            return False
        if not allow_private and (ip.is_private or ip.is_loopback):
            return False
    return True


def _health_state(reachable: bool, unauthorized: bool) -> str:
    if not reachable:
        return "unreachable"
    return "starting" if unauthorized else "healthy"


def detect() -> dict[str, Any]:
    """Probe the fixed candidate list for a reachable HomePilot. Returns the
    first hit plus a per-candidate diagnostic trail for the 'Looking for
    HomePilot…' UI. Never raises."""
    probes: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for api_url, browser_url, kind in DETECT_CANDIDATES:
        if not _ssrf_ok(api_url):
            probes.append({"apiUrl": api_url, "health": "blocked"})
            continue
        health = HomePilotClient(base_url=api_url, api_key=None, timeout=_DETECT_TIMEOUT).health()
        unauthorized = health.error == "unauthorized"
        state = _health_state(health.reachable, unauthorized)
        probes.append({"apiUrl": api_url, "health": state})
        if health.reachable and found is None:
            found = {
                "apiUrl": api_url,
                "browserUrl": browser_url,
                "health": state,
                "version": str((health.payload or {}).get("version") or "") or None,
                "installationType": kind,
            }
    return {"detected": found is not None, "instance": found, "probes": probes}


def _check(key: str, ok: bool, label: str) -> dict[str, Any]:
    return {"key": key, "ok": bool(ok), "label": label}


def test_address(base_url: str, api_key: str | None, *, allow_private: bool = True) -> dict[str, Any]:
    """Run a connection checklist against an address without persisting anything.
    Returns per-step results (reachable / authenticated / personas / chat /
    version) and counts. Never echoes the API key."""
    if not base_url or not _ssrf_ok(base_url, allow_private=allow_private):
        return {
            "ok": False,
            "code": "blocked_address",
            "checks": [_check("reachable", False, "Address is not allowed")],
            "personaCount": 0,
            "chatCount": 0,
            "version": None,
            "chatMode": "unknown",
        }

    client = HomePilotClient(base_url=base_url, api_key=(api_key or None), timeout=_TEST_TIMEOUT)
    health = client.health()
    unauthorized = health.error == "unauthorized"
    reachable = health.reachable
    authed = reachable and not unauthorized

    checks = [
        _check("reachable", reachable, "HomePilot is reachable"),
        _check("authenticated", authed,
               "Authentication succeeded" if authed else "Authentication failed"),
    ]

    persona_projects: list[dict[str, Any]] = []
    persona_models: list[str] = []
    caps = None
    if authed:
        persona_projects = [p for p in client.list_projects() if p.get("project_type") == "persona"]
        persona_models = [m for m in client.list_models() if is_persona_model(m)]
        caps = client.capabilities()

    checks.append(_check("personas", bool(persona_projects),
                         f"{len(persona_projects)} personas were found" if authed else "Persona projects unavailable"))
    checks.append(_check("chat", bool(persona_models),
                         "Agent chat API is available" if persona_models else "No personas are enabled for chat"))
    version = str((health.payload or {}).get("version") or "") or None
    checks.append(_check("version", authed, f"HomePilot {version}" if version else "HomePilot version detected"))

    return {
        "ok": authed,
        "code": "connected" if authed else ("unauthorized" if unauthorized else "unreachable"),
        "checks": checks,
        "personaCount": len(persona_projects),
        "chatCount": len(persona_models),
        "version": version,
        "chatMode": "bridge" if caps else ("chat_only" if authed else "unknown"),
    }
