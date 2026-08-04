"""Gmail / Microsoft mailbox OAuth — authorization-code flow with PKCE + XOAUTH2.

The complete server-side flow the wizard needs:

  start    → generate a one-time ``state`` + PKCE verifier/challenge, persist the
             pending session (workspace, provider, verifier, expiry, return URL)
             in the credential store, and return the provider authorization URL.
  callback → validate + CONSUME the state (one-time CSRF), exchange the code
             (with the PKCE verifier), fetch the account identity, store the
             tokens ONLY in the credential store, create/update the
             ``MailboxConnection``, and hand back a redirect target.
  refresh  → exchange a stored refresh token for a fresh access token when it has
             expired, so IMAP/SMTP XOAUTH2 keeps working.

Secrets (client secret, access/refresh tokens) never leave the backend and are
never logged. Outbound calls go through :func:`_http`, whose transport tests can
replace with an ``httpx.MockTransport``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from daypilot_knowledge.db import MailboxConnection
from daypilot_orchestrator.integrations.credentials import credential_store

# Per-provider OAuth + mailbox endpoints. Scopes cover IMAP + SMTP XOAUTH2 plus
# the identity claim, and offline access for a refresh token.
_PROVIDERS: dict[str, dict[str, Any]] = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": ("https://mail.google.com/ "
                  "https://www.googleapis.com/auth/userinfo.email openid"),
        "imap": ("imap.gmail.com", 993, "ssl"),
        "smtp": ("smtp.gmail.com", 587, "starttls"),
        "extra_authorize": {"access_type": "offline", "prompt": "select_account consent"},
    },
    "microsoft": {
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo": None,  # identity comes from the id_token claim
        "scope": ("https://outlook.office.com/IMAP.AccessAsUser.All "
                  "https://outlook.office.com/SMTP.Send offline_access openid email"),
        "imap": ("outlook.office365.com", 993, "ssl"),
        "smtp": ("smtp.office365.com", 587, "starttls"),
        "extra_authorize": {"prompt": "select_account"},
    },
}

_STATE_TTL_SECONDS = 600  # a pending authorization is valid for 10 minutes
_HTTP_TIMEOUT = 20.0

# Injectable transport for tests (httpx.MockTransport). None → real network.
_transport: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = transport


def _http() -> httpx.Client:
    return httpx.Client(timeout=_HTTP_TIMEOUT, transport=_transport)


# ---- provider config --------------------------------------------------------

def normalize_provider(provider: str) -> str | None:
    p = (provider or "").lower()
    if p in ("google", "gmail"):
        return "google"
    if p in ("microsoft", "outlook", "office365", "ms"):
        return "microsoft"
    return None


def _client_id(key: str) -> str:
    if key == "google":
        return os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    return os.getenv("MS_GRAPH_CLIENT_ID") or os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "")


def _client_secret(key: str) -> str:
    if key == "google":
        return os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    return os.getenv("MS_GRAPH_CLIENT_SECRET") or os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "")


def _redirect_uri(key: str) -> str:
    if key == "google":
        return os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    return (os.getenv("MS_GRAPH_REDIRECT_URI") or os.getenv("MICROSOFT_OAUTH_REDIRECT_URI", "")).strip()


def is_configured(key: str) -> bool:
    return bool(_client_id(key))


# ---- PKCE + one-time state --------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def _state_ref(state: str) -> str:
    return f"email-oauth-state:{state}"


def _store_state(state: str, payload: dict[str, Any]) -> None:
    credential_store().put(_state_ref(state), payload)


def _consume_state(state: str) -> dict[str, Any] | None:
    """Read AND delete the pending session — state is one-time. Returns None if
    unknown or expired."""
    ref = _state_ref(state)
    try:
        data = credential_store().get(ref) or None
    except Exception:  # noqa: BLE001
        data = None
    if data is None:
        return None
    try:
        credential_store().delete(ref)
    except Exception:  # noqa: BLE001
        pass
    if float(data.get("expires_at", 0)) < time.time():
        return None
    return data


# ---- start ------------------------------------------------------------------

def build_authorization(workspace_id: str, key: str, return_url: str | None = None) -> dict[str, Any]:
    """Create the authorization URL + persist the pending PKCE/state session."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    _store_state(state, {
        "workspace_id": workspace_id,
        "provider": key,
        "verifier": verifier,
        "return_url": return_url or "",
        "expires_at": time.time() + _STATE_TTL_SECONDS,
    })
    cfg = _PROVIDERS[key]
    params = {
        "response_type": "code",
        "client_id": _client_id(key),
        "scope": cfg["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **cfg["extra_authorize"],
    }
    redirect = _redirect_uri(key)
    if redirect:
        params["redirect_uri"] = redirect
    return {
        "available": True,
        "provider": key,
        "authorizationUrl": f"{cfg['authorize']}?{urlencode(params)}",
        "state": state,
    }


# ---- token exchange + identity ----------------------------------------------

def _token_request(key: str, data: dict[str, str]) -> dict[str, Any]:
    cfg = _PROVIDERS[key]
    body = {"client_id": _client_id(key), **data}
    secret = _client_secret(key)
    if secret:
        body["client_secret"] = secret
    redirect = _redirect_uri(key)
    if redirect and "redirect_uri" not in body and data.get("grant_type") == "authorization_code":
        body["redirect_uri"] = redirect
    with _http() as c:
        r = c.post(cfg["token"], data=body,
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        return r.json()


def _jwt_email(id_token: str) -> str:
    """Best-effort email from an id_token claim. The token came directly from the
    provider's TLS token endpoint, so it's trusted for identity display; we don't
    re-verify the signature here."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload).decode())
    except (ValueError, IndexError, json.JSONDecodeError):
        return ""
    return str(claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "")


def _identity(key: str, token: dict[str, Any]) -> str:
    cfg = _PROVIDERS[key]
    if cfg["userinfo"] and token.get("access_token"):
        try:
            with _http() as c:
                r = c.get(cfg["userinfo"],
                          headers={"Authorization": f"Bearer {token['access_token']}"})
                r.raise_for_status()
                data = r.json()
            email = str(data.get("email") or "")
            if email:
                return email
        except (httpx.HTTPError, ValueError):
            pass
    return _jwt_email(token.get("id_token", ""))


# ---- callback ---------------------------------------------------------------

def _hosts_for(key: str) -> dict[str, Any]:
    cfg = _PROVIDERS[key]
    ih, ip, isec = cfg["imap"]
    sh, sp, ssec = cfg["smtp"]
    return {"imap_host": ih, "imap_port": ip, "imap_security": isec,
            "smtp_host": sh, "smtp_port": sp, "smtp_security": ssec}


def _store_tokens(ref: str, key: str, email: str, token: dict[str, Any],
                  prior_refresh: str = "") -> float:
    """Persist tokens in the credential store; return the access-token expiry
    (epoch seconds). Providers omit refresh_token on re-consent, so keep the
    prior one when absent."""
    expires_in = float(token.get("expires_in", 3600))
    expires_at = time.time() + expires_in
    credential_store().put(ref, {
        "auth": "xoauth2",
        "provider": key,
        "email": email,
        "access_token": token.get("access_token", ""),
        "refresh_token": token.get("refresh_token") or prior_refresh,
        "expires_at": expires_at,
    })
    return expires_at


def handle_callback(session: Session, provider_hint: str, code: str, state: str) -> dict[str, Any]:
    """Exchange the code and connect the mailbox. Returns
    {ok, workspaceId, email, returnUrl} or {ok:False, error}."""
    pending = _consume_state(state)
    if pending is None:
        return {"ok": False, "error": "invalid_state"}
    key = pending["provider"]
    if provider_hint and normalize_provider(provider_hint) not in (None, key):
        return {"ok": False, "error": "provider_mismatch"}
    if not code:
        return {"ok": False, "error": "missing_code"}

    try:
        token = _token_request(key, {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": pending["verifier"],
        })
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "error": "token_exchange_failed"}

    email = _identity(key, token)
    workspace_id = pending["workspace_id"]

    from .mail_setup import _get  # local import avoids a cycle
    row = _get(session, workspace_id)
    if row is None:
        row = MailboxConnection(workspace_id=workspace_id, provider=key)
        session.add(row)
        session.flush()
    row.provider = key
    row.email_address = email
    row.username = email
    hosts = _hosts_for(key)
    row.imap_host, row.imap_port, row.imap_security = hosts["imap_host"], hosts["imap_port"], hosts["imap_security"]
    row.smtp_host, row.smtp_port, row.smtp_security = hosts["smtp_host"], hosts["smtp_port"], hosts["smtp_security"]
    ref = row.secret_reference or f"mailbox:{row.id}"
    row.secret_reference = ref
    expires_at = _store_tokens(ref, key, email, token)
    row.oauth_expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    row.status = "connected"
    row.last_error_code = None
    session.flush()
    return {"ok": True, "workspaceId": workspace_id, "email": email,
            "returnUrl": pending.get("return_url") or ""}


# ---- refresh + XOAUTH2 for the adapter --------------------------------------

def xoauth2_credentials(session: Session, row: MailboxConnection) -> tuple[str, str] | None:
    """(email, access_token) for a connected OAuth mailbox, refreshing the token
    if it has expired. None if this isn't an OAuth connection or refresh fails."""
    if not row.secret_reference:
        return None
    try:
        secret = credential_store().get(row.secret_reference) or {}
    except Exception:  # noqa: BLE001
        return None
    if secret.get("auth") != "xoauth2":
        return None
    email = secret.get("email", "")
    if float(secret.get("expires_at", 0)) > time.time() + 60:
        return email, secret.get("access_token", "")

    # Expired (or about to) → refresh.
    key = secret.get("provider") or "google"
    refresh = secret.get("refresh_token", "")
    if not refresh:
        return (email, secret.get("access_token", "")) if secret.get("access_token") else None
    try:
        token = _token_request(key, {"grant_type": "refresh_token", "refresh_token": refresh})
    except (httpx.HTTPError, ValueError):
        return None
    expires_at = _store_tokens(row.secret_reference, key, email, token, prior_refresh=refresh)
    row.oauth_expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    session.flush()
    return email, token.get("access_token", "")


def build_xoauth2_string(user: str, access_token: str) -> str:
    """The SASL XOAUTH2 initial-client-response (before base64), per the Google /
    Microsoft spec: ``user=<email>^Aauth=Bearer <token>^A^A``."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"
