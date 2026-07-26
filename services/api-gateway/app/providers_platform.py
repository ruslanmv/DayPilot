"""Backend-owned AI provider connections (Batch 2).

The backend is the source of truth for provider state, the active provider, and
the selected model — the browser never fabricates a connection. Local Ollabridge
is detected by real probes; Ollabridge Cloud is authenticated server-side. Keys
and tokens are held by the credential store (secret-by-reference) and never
returned to the browser or written to logs.

State machine (per connection):
    unconfigured | testing | connected | degraded | offline | unauthorized | expired
"""
from __future__ import annotations

import ipaddress
import os
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import ProviderConnection
from daypilot_knowledge.db.models import utcnow
from daypilot_models.ollabridge_client import (
    CLOUD_DEFAULT_URL,
    LOCAL_DEFAULT_URL,
    OllabridgeConnector,
    normalize_gateway_root,
)
from daypilot_orchestrator.integrations.credentials import credential_store

LOCAL = "local"
CLOUD = "ollabridge_cloud"

# The canonical Cloud API (overridable). The HF Space is only a compat override.
CLOUD_API_BASE = os.getenv("OLLABRIDGE_CLOUD_URL", CLOUD_DEFAULT_URL)


def _cloud_auth_root() -> str:
    """The cloud gateway root that hosts ``/v1/auth/login`` and ``/v1/auth/me``.

    ``CLOUD_API_BASE`` is the OpenAI base (ends in ``/v1``); the JSON auth routes
    are mounted at the *root* (router prefix ``/v1/auth``). Posting ``/v1/auth/login``
    against a ``…/v1`` base would double the prefix (``…/v1/v1/auth/login`` → 404,
    the "didn't respond like Ollabridge" error), so we normalise to the root.
    """
    return normalize_gateway_root(CLOUD_API_BASE)


def _cloud_web_base() -> str:
    """Base URL of the OllaBridge Cloud *web* app (login/register pages).

    Defaults to the API host (same origin serves the web dashboard) and is
    overridable for split web/API deployments via ``OLLABRIDGE_CLOUD_WEB_URL``.
    """
    explicit = os.getenv("OLLABRIDGE_CLOUD_WEB_URL", "").strip().rstrip("/")
    return explicit or _cloud_auth_root()


def cloud_web_login_url() -> str:
    return f"{_cloud_web_base()}/login"


def cloud_web_register_url() -> str:
    return f"{_cloud_web_base()}/register"


# ---- SSRF guard for user-entered local URLs ---------------------------------

def _is_allowed_local(url: str) -> bool:
    """Local provider URLs must resolve to loopback or private ranges only, so a
    user-entered URL can't be used for server-side request forgery."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A hostname that isn't an IP: only allow the explicit localhost above.
        return False
    return ip.is_loopback or ip.is_private


# ---- persistence helpers ----------------------------------------------------

def _get_or_create(session: Session, workspace_id: str, kind: str) -> ProviderConnection:
    row = session.execute(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == workspace_id, ProviderConnection.kind == kind
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProviderConnection(
            workspace_id=workspace_id, kind=kind, state="unconfigured",
            base_url=(LOCAL_DEFAULT_URL if kind == LOCAL else CLOUD_API_BASE),
        )
        session.add(row)
        session.flush()
    return row


def _public(row: ProviderConnection) -> dict[str, Any]:
    """Safe view — never includes secrets."""
    return {
        "kind": row.kind,
        "baseUrl": row.base_url,
        "state": row.state,
        "active": row.active,
        "account": {
            "subject": row.account_subject,
            "email": row.account_email,
            "displayName": row.account_display_name,
        } if row.account_email or row.account_subject else None,
        "defaultModel": row.default_model,
        "modelsCount": row.models_count,
        "lastTestedAt": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "lastLatencyMs": row.last_latency_ms,
        "lastErrorCode": row.last_error_code,
    }


def status(session: Session, workspace_id: str) -> dict[str, Any]:
    local = _get_or_create(session, workspace_id, LOCAL)
    cloud = _get_or_create(session, workspace_id, CLOUD)
    active = next((c.kind for c in (local, cloud) if c.active), None)
    session.flush()
    return {
        "connections": [_public(local), _public(cloud)],
        "active": active,
        # Deep links to the OllaBridge Cloud web app so the UI can offer
        # "log in on the web" (Google/SSO, password reset, create account).
        "cloudLoginUrl": cloud_web_login_url(),
        "cloudRegisterUrl": cloud_web_register_url(),
    }


# ---- local Ollabridge -------------------------------------------------------

def _default_route_gateway() -> str | None:
    """The eth0 default-route gateway from ``/proc/net/route``.

    On WSL2 this gateway IS the Windows host (services bound to 0.0.0.0 on the
    host are reachable there), which is the canonical way to reach a Windows-side
    gateway from inside WSL2 — more reliable than the resolv.conf nameserver,
    which newer WSL builds set to a DNS-tunnel address (10.255.255.254) that does
    not carry arbitrary TCP.
    """
    try:
        with open("/proc/net/route", encoding="utf-8") as fh:
            for line in fh.readlines()[1:]:
                fields = line.split()
                # Destination 00000000 + RTF_GATEWAY flag (0x2) == default route.
                if len(fields) >= 4 and fields[1] == "00000000" and int(fields[3], 16) & 0x2:
                    gw = fields[2]  # little-endian hex, e.g. "0160D9AC"
                    octets = [str(int(gw[i:i + 2], 16)) for i in range(0, 8, 2)]
                    return ".".join(reversed(octets))
    except (OSError, ValueError):
        pass
    return None


def _host_gateway_ips() -> list[str]:
    """Best-effort host addresses reachable from inside WSL2/Docker.

    DayPilot may run in WSL2 or a container while the Ollabridge gateway runs on
    the Windows/host side. From there ``localhost`` is the VM/container itself, so
    a loopback gateway URL connection-refuses even though the gateway is up. These
    aliases point back at the host; we try them only after a loopback URL fails.
    Ordered most-reliable-first: the default route (WSL2's Windows host), then any
    private resolv.conf nameserver, then the Docker Desktop alias.
    """
    ips: list[str] = []
    gw = _default_route_gateway()
    if gw:
        try:
            if ipaddress.ip_address(gw).is_private:
                ips.append(gw)
        except ValueError:
            pass
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:  # WSL2 (legacy): nameserver == host
            for line in fh:
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            if ipaddress.ip_address(parts[1]).is_private:
                                ips.append(parts[1])
                        except ValueError:
                            pass
    except OSError:
        pass
    ips.append("host.docker.internal")
    # De-dup, preserve order.
    seen: set[str] = set()
    uniq: list[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            uniq.append(ip)
    return uniq


def _loopback_candidates(root: str) -> list[str]:
    """The gateway root plus host-side fallbacks when it's a loopback address."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(root)
    host = (parts.hostname or "").lower()
    out = [root]
    if host in ("localhost", "127.0.0.1", "::1"):
        port = f":{parts.port}" if parts.port else ""
        for alt in _host_gateway_ips():
            out.append(urlunsplit((parts.scheme, f"{alt}{port}", parts.path, "", "")))
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _probe_one(root: str, api_key: str | None) -> dict[str, Any]:
    """Probe a single normalized gateway root, health-first.

    ``/health`` is public (no key, no loopback requirement), so it — not
    ``/v1/models`` — decides "is the gateway running?". That's the fix for the
    false "Ollabridge isn't running at that address": the model list is gated
    (``local-trust`` only bypasses auth for *loopback* callers, and ``required``
    mode always needs a key), so probing models first made a healthy but
    key-gated gateway look dead. Now a reachable gateway missing only its key is
    reported as ``key_required``, not offline.
    """
    import time as _time

    import httpx

    key = (api_key or "").strip() or None
    auth = {"Authorization": f"Bearer {key}", "X-API-Key": key} if key else {}

    start = _time.perf_counter()
    try:
        with httpx.Client(base_url=root, timeout=5.0) as c:
            health = c.get("/health")
    except httpx.ConnectError:
        return {"code": "connection_refused", "latencyMs": None, "models": []}
    except httpx.TimeoutException:
        return {"code": "timeout", "latencyMs": None, "models": []}
    except Exception:  # noqa: BLE001
        return {"code": "connection_refused", "latencyMs": None, "models": []}

    latency = round((_time.perf_counter() - start) * 1000, 1)
    if health.status_code >= 500:
        return {"code": "invalid_response", "latencyMs": None, "models": []}
    try:  # a real Ollabridge /health answers JSON
        health.json()
    except ValueError:
        return {"code": "invalid_response", "latencyMs": None, "models": []}

    # Reachable & identified. Enumerate models (needs a key unless loopback+local-trust).
    try:
        with httpx.Client(base_url=root, timeout=6.0, headers=auth) as c:
            r = c.get("/v1/models")
    except httpx.HTTPError:
        return {"code": "no_models", "latencyMs": latency, "models": []}

    if r.status_code in (401, 403):
        # Reachable, but the list is gated. Tell the two cases apart: nothing
        # supplied ("add your key") vs. a wrong key supplied ("key rejected").
        return {"code": "unauthorized" if key else "key_required", "latencyMs": latency, "models": []}
    if r.status_code == 200:
        try:
            data = r.json()
        except ValueError:
            data = {}
        found = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return {"code": "connected" if found else "no_models", "latencyMs": latency, "models": found}
    return {"code": "invalid_response", "latencyMs": latency, "models": []}


def _probe_local(base_url: str, api_key: str | None) -> dict[str, Any]:
    """Return {code, latencyMs, models, resolvedBaseUrl}. Health-first, with
    loopback→host fallbacks so DayPilot-in-WSL/Docker can reach a host gateway.

    The connector-level normalization means a stored ``…/11435/v1`` and a bare
    root both probe ``/health`` and ``/v1/models`` correctly (no ``/v1/v1/…``).
    """
    root0 = normalize_gateway_root(base_url)
    # Reachable outcomes we can stop on (anything that proves a gateway is there).
    reachable_codes = {"connected", "no_models", "unauthorized", "key_required"}
    fallback: dict[str, Any] | None = None
    for root in _loopback_candidates(root0):
        res = _probe_one(root, api_key)
        res["resolvedBaseUrl"] = root + "/v1"
        if res["code"] in reachable_codes:
            return res
        fallback = fallback or res
    if fallback is None:
        fallback = {"code": "connection_refused", "latencyMs": None, "models": []}
    fallback.setdefault("resolvedBaseUrl", root0 + "/v1")
    return fallback


def local_test(session: Session, workspace_id: str, base_url: str, api_key: str | None) -> dict[str, Any]:
    if not _is_allowed_local(base_url):
        return {"code": "invalid_response", "detail": "url_not_allowed"}
    row = _get_or_create(session, workspace_id, LOCAL)
    row.state = "testing"
    session.flush()
    result = _probe_local(base_url, api_key)
    code = result["code"]
    # Persist the host that actually answered (may be a WSL/Docker host fallback),
    # so later chat calls reuse the reachable address rather than a dead loopback.
    row.base_url = result.get("resolvedBaseUrl") or base_url
    row.last_tested_at = utcnow()
    row.last_latency_ms = int(result["latencyMs"]) if result["latencyMs"] else None
    row.last_error_code = None if code == "connected" else code
    row.models_count = len(result["models"])
    if code == "connected":
        row.state = "connected"
    elif code == "no_models":
        row.state = "degraded"  # reachable & authorized, just no models loaded yet
    elif code in ("unauthorized", "key_required"):
        row.state = "unauthorized"
    else:
        row.state = "offline"
    session.flush()
    return {"code": code, "models": result["models"], "connection": _public(row)}


def local_connect(session: Session, workspace_id: str, base_url: str, api_key: str | None) -> dict[str, Any]:
    """Only persist a local connection after a successful test."""
    out = local_test(session, workspace_id, base_url, api_key)
    if out["code"] != "connected":
        return out
    row = _get_or_create(session, workspace_id, LOCAL)
    ref = f"provider:{row.id}"
    if api_key:
        credential_store().put(ref, {"api_key": api_key})
        row.secret_reference = ref
    if not row.default_model and out["models"]:
        row.default_model = out["models"][0]
    session.flush()
    return {"code": "connected", "connection": _public(row)}


# ---- Ollabridge Cloud (server-side auth) ------------------------------------

def cloud_login(session: Session, workspace_id: str, email: str, password: str) -> dict[str, Any]:
    """Exchange email/password with Ollabridge Cloud server-side. The password
    is transient (never stored); the returned token is placed in the credential
    store and validated via /v1/auth/me. Honest error codes on failure."""
    import httpx

    row = _get_or_create(session, workspace_id, CLOUD)
    row.state = "testing"
    session.flush()
    # Auth routes live at the cloud *root* (/v1/auth/login, /v1/auth/me), not
    # under the OpenAI /v1 base — normalize so we don't double the prefix.
    auth_root = _cloud_auth_root()
    try:
        with httpx.Client(base_url=auth_root, timeout=8.0) as c:
            resp = c.post("/v1/auth/login", json={"email": email, "password": password})
            if resp.status_code in (401, 403):
                row.state = "unauthorized"
                row.last_error_code = "unauthorized"
                session.flush()
                return {"code": "unauthorized"}
            resp.raise_for_status()
            body = resp.json()
            token = body.get("token") or body.get("access_token")
            if not token:
                row.state = "offline"
                row.last_error_code = "invalid_response"
                session.flush()
                return {"code": "invalid_response"}
            me = c.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    except httpx.ConnectError:
        return _cloud_fail(session, row, "connection_refused")
    except httpx.TimeoutException:
        return _cloud_fail(session, row, "timeout")
    except Exception:  # noqa: BLE001
        return _cloud_fail(session, row, "invalid_response")

    ref = f"provider:{row.id}"
    credential_store().put(ref, {"token": token})
    row.secret_reference = ref
    # Cloud /v1/auth/me returns {user_id, email, display_name, ...}. Fall back to
    # the login response and older field names so we stay tolerant.
    row.account_subject = str(me.get("user_id") or body.get("user_id") or me.get("sub") or me.get("id") or "")
    row.account_email = me.get("email") or body.get("email") or email
    row.account_display_name = me.get("display_name") or me.get("name") or None
    row.state = "connected"
    row.last_error_code = None
    row.last_tested_at = utcnow()
    _load_cloud_models(row, token)
    session.flush()
    return {"code": "connected", "connection": _public(row)}


def _cloud_fail(session: Session, row: ProviderConnection, code: str) -> dict[str, Any]:
    row.state = "offline"
    row.last_error_code = code
    session.flush()
    return {"code": code}


def _load_cloud_models(row: ProviderConnection, token: str) -> None:
    import httpx

    try:
        conn = OllabridgeConnector(base_url=CLOUD_API_BASE, api_key=token)
        models = conn.list_models()
        row.models_count = len(models)
        if not row.default_model and models:
            row.default_model = models[0]
    except (httpx.HTTPError, ValueError):
        pass


def cloud_models(session: Session, workspace_id: str) -> dict[str, Any]:
    row = _get_or_create(session, workspace_id, CLOUD)
    if row.state != "connected" or not row.secret_reference:
        return {"models": [], "state": row.state}
    token = credential_store().get(row.secret_reference).get("token", "")
    try:
        models = OllabridgeConnector(base_url=CLOUD_API_BASE, api_key=token).list_models()
    except Exception:  # noqa: BLE001
        models = []
    return {"models": models}


def cloud_logout(session: Session, workspace_id: str) -> dict[str, Any]:
    row = _get_or_create(session, workspace_id, CLOUD)
    if row.secret_reference:
        credential_store().delete(row.secret_reference)
    row.secret_reference = None
    row.state = "unconfigured"
    row.account_subject = row.account_email = row.account_display_name = None
    row.default_model = None
    row.models_count = 0
    if row.active:
        row.active = False
        _get_or_create(session, workspace_id, LOCAL).active = True
    session.flush()
    return {"loggedOut": True, "connection": _public(row)}


# ---- active provider + model ------------------------------------------------

def set_active(session: Session, workspace_id: str, kind: str) -> dict[str, Any]:
    if kind not in (LOCAL, CLOUD):
        raise ValueError("unknown_provider")
    local = _get_or_create(session, workspace_id, LOCAL)
    cloud = _get_or_create(session, workspace_id, CLOUD)
    target = local if kind == LOCAL else cloud
    if target.state != "connected":
        raise PermissionError("provider_not_connected")
    local.active = kind == LOCAL
    cloud.active = kind == CLOUD
    session.flush()
    return {"active": kind, "connection": _public(target)}


def set_default_model(session: Session, workspace_id: str, kind: str, model: str) -> dict[str, Any]:
    row = _get_or_create(session, workspace_id, kind)
    row.default_model = model
    session.flush()
    return {"connection": _public(row)}


def _now() -> datetime:
    return utcnow()
