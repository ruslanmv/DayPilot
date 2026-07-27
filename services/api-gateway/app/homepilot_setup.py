"""HomePilot setup: auto-detection + connection diagnostics (backend-only).

The guided setup wizard needs to (a) find a HomePilot installation and (b) run a
human-readable connection checklist against an address. Both happen here, on the
backend — the browser never probes the network (contract rule 4).

Detection is deliberately broad because HomePilot ships in several topologies:

  * Desktop app / single Docker container — UI + proxied API on ``7860`` (API
    under ``/api``).
  * Full Compose / source (``make run``) — backend API on ``8000``, frontend on
    ``3000``.

and DayPilot may be reaching it across a boundary: same machine (loopback), a
Docker container (``homepilot`` service name, ``host.docker.internal``, the
bridge gateway ``172.17.0.1``), or WSL2 (the Windows/WSL host, reachable via the
default-route gateway and the ``/etc/resolv.conf`` nameserver). So candidates are
the product of *discovered hosts* × *port profiles*, and each is probed on both
``/health`` and the OpenAI-compatible ``/v1/models`` (some builds answer only one)
— in parallel, so a wide sweep still returns quickly.

Security:
  * Detection only ever tries code-owned hosts + runtime-discovered LAN gateways;
    every candidate still passes ``_ssrf_ok`` (cloud-metadata / link-local
    blocked).
  * A user-supplied address is passed through ``_ssrf_ok`` first.
  * The API key is never echoed back to the caller and never logged.
"""
from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import struct
from typing import Any
from urllib.parse import urlsplit

from daypilot_orchestrator.homepilot.client import HomePilotClient
from daypilot_orchestrator.homepilot.contracts import is_persona_model

# Port profiles: (port, api_path, browser_port, installation_type). The desktop /
# single-container build proxies the API under /api on 7860; the compose/source
# build serves the API at the root on 8000 and the UI on 3000.
_PORT_PROFILES: list[tuple[int, str, int, str]] = [
    (7860, "/api", 7860, "desktop"),
    (8000, "", 3000, "docker_compose"),
]

# Hosts always tried, in priority order: the Docker service name, the Docker
# Desktop / WSL2 host alias, then loopback. Runtime-discovered gateways are
# appended (WSL2 host, default route, docker bridge).
_STATIC_HOSTS = ["homepilot", "host.docker.internal", "127.0.0.1", "localhost"]
_DOCKER_BRIDGE_HOSTS = ["172.17.0.1"]

# Never connect to these — cloud instance-metadata and link-local ranges. Blocked
# regardless of the allowPrivate intent (SSRF hardening).
_METADATA_HOSTS = {"169.254.169.254", "100.100.100.200", "metadata.google.internal", "metadata"}
_DETECT_TIMEOUT = 1.8
_TEST_TIMEOUT = 8.0
_MAX_CANDIDATES = 24


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


# ---- host discovery (WSL2 / Docker → host reachability) ---------------------

def _default_gateway_ips() -> list[str]:
    """Default-route gateway IPs from /proc/net/route. In a Docker container this
    is the bridge gateway (the host); in WSL2 it points at the WSL host."""
    ips: list[str] = []
    try:
        with open("/proc/net/route") as f:
            lines = f.read().splitlines()[1:]
    except OSError:
        return ips
    for line in lines:
        fields = line.split()
        if len(fields) >= 3 and fields[1] == "00000000" and fields[2] not in ("", "00000000"):
            try:
                ips.append(socket.inet_ntoa(struct.pack("<L", int(fields[2], 16))))
            except (ValueError, OSError):
                continue
    return ips


def _resolv_nameservers() -> list[str]:
    """Non-loopback nameservers from /etc/resolv.conf. On WSL2 this is typically
    the Windows host IP, which is where a host-side HomePilot is reachable."""
    ips: list[str] = []
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver" and not parts[1].startswith("127."):
                    ips.append(parts[1])
    except OSError:
        pass
    return ips


def _is_private_ip(ip: str) -> bool:
    """A WSL2/Docker host is always a private (or loopback) address; a public IP
    from discovery (e.g. a public DNS resolver in resolv.conf) is never a
    HomePilot host, so we never probe it."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return (addr.is_private or addr.is_loopback) and not addr.is_link_local


def _discovered_hosts() -> list[str]:
    """Runtime-discovered private host addresses (WSL2/Docker gateways), deduped.
    Public IPs are dropped — a host-side HomePilot is always on a private LAN."""
    out: list[str] = []
    for ip in (*_resolv_nameservers(), *_default_gateway_ips(), *_DOCKER_BRIDGE_HOSTS):
        if ip and ip not in out and _is_private_ip(ip):
            out.append(ip)
    return out


# Hosts a browser can never resolve — translate them to localhost for the
# human-facing (gallery) URL. In the common local/WSL/Docker-Desktop setup the
# browser runs on the same host that publishes HomePilot's ports.
_NON_BROWSER_HOSTS = {"homepilot", "host.docker.internal", "0.0.0.0", "::", "[::]"}


def _browser_host(host: str) -> str:
    return "localhost" if host.lower() in _NON_BROWSER_HOSTS else host


def _installation_type(host: str, base_kind: str) -> str:
    """Refine the topology hint by which host answered."""
    if base_kind == "docker_compose":
        return "docker_compose"
    if host == "homepilot":
        return "single_container"
    if host in ("host.docker.internal", *_DOCKER_BRIDGE_HOSTS) or host in _discovered_hosts():
        return "remote"  # reached across a container/WSL boundary
    return "desktop"


def candidates() -> list[tuple[str, str, str]]:
    """(api_url, browser_url, installation_type) for every host × port profile,
    SSRF-filtered and capped. Static hosts first, discovered gateways after."""
    hosts = list(_STATIC_HOSTS)
    for h in _discovered_hosts():
        if h not in hosts:
            hosts.append(h)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for host in hosts:
        for port, api_path, browser_port, base_kind in _PORT_PROFILES:
            api = f"http://{host}:{port}{api_path}"
            if api in seen or not _ssrf_ok(api):
                continue
            seen.add(api)
            browser = f"http://{_browser_host(host)}:{browser_port}"
            out.append((api, browser, _installation_type(host, base_kind)))
            if len(out) >= _MAX_CANDIDATES:
                return out
    return out


def _probe(api_url: str) -> dict[str, Any]:
    """Probe one candidate on /health and, as a fallback, /v1/models (some builds
    answer only one). ``homepilot`` is True when it looks like HomePilot — either
    endpoint responded — so a live-but-key-gated instance still counts."""
    client = HomePilotClient(base_url=api_url, api_key=None, timeout=_DETECT_TIMEOUT)
    health = client.health()
    unauthorized = health.error == "unauthorized"
    reachable = health.reachable
    version = str((health.payload or {}).get("version") or "") or None
    is_hp = reachable
    if not reachable:
        # /health may be absent (or on a different path) on some builds — the
        # OpenAI-compatible model list is the same endpoint OllaBridge uses.
        if client.list_models():
            reachable = True
            is_hp = True
    return {
        "apiUrl": api_url,
        "health": _health_state(reachable, unauthorized),
        "reachable": reachable,
        "unauthorized": unauthorized,
        "homepilot": is_hp,
        "version": version,
    }


def detect() -> dict[str, Any]:
    """Sweep every host × port candidate in parallel for a reachable HomePilot.
    Returns the best hit (respecting candidate priority) plus a per-candidate
    diagnostic trail for the 'Looking for HomePilot…' UI. Never raises."""
    cands = candidates()
    results_by_url: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(cands) or 1)) as pool:
        futures = {pool.submit(_probe, api): api for api, _b, _k in cands}
        for fut in concurrent.futures.as_completed(futures):
            api = futures[fut]
            try:
                results_by_url[api] = fut.result()
            except Exception:  # noqa: BLE001 - a probe failure is just "unreachable"
                results_by_url[api] = {"apiUrl": api, "health": "unreachable", "reachable": False,
                                       "unauthorized": False, "homepilot": False, "version": None}

    # Keep probes in candidate-priority order; pick the first reachable+HomePilot
    # hit, else the first merely-reachable one.
    probes = [results_by_url[api] for api, _b, _k in cands if api in results_by_url]
    found = None
    for api, browser, kind in cands:
        r = results_by_url.get(api)
        if r and r["reachable"] and (r["homepilot"] or found is None):
            found = {"apiUrl": api, "browserUrl": browser, "health": r["health"],
                     "version": r["version"], "installationType": kind}
            if r["homepilot"]:
                break
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
