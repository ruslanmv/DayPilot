"""Connecting a calendar — Microsoft 365 and Google, authorization-code + PKCE.

This reuses the PKCE, one-time-state and token-exchange machinery that already
backs mailbox OAuth (:mod:`app.mail_oauth`) rather than growing a second
implementation of the same flow. What differs is only what it asks for and what
it produces:

* **Scopes are read-only.** ``Calendars.Read`` / ``calendar.readonly`` is
  everything the MVP needs — import meetings, plan around them, prepare briefs.
  Writing to a calendar is a separate, later consent. DayPilot approval-gates
  writes internally regardless, but an internal gate is not a reason to hold a
  permission we are not using.
* **The result is an IntegrationConnection**, not a MailboxConnection, so a
  calendar is governed by the same Integration Gateway as Slack and GitHub:
  reads run, writes open an approval.

Tokens are written to the credential store keyed by connection id and never to
the database, a log, or a response body.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import IntegrationConnection
from daypilot_orchestrator.calendar.connections import GOOGLE, LEGACY_GOOGLE, MICROSOFT
from daypilot_orchestrator.integrations.credentials import credential_store

from . import mail_oauth

#: Read-only to start. `offline_access` / `access_type=offline` is what makes a
#: refresh token available, so a connection survives the first hour.
PROVIDERS: dict[str, dict[str, Any]] = {
    MICROSOFT: {
        "label": "Microsoft Outlook",
        "oauth_key": "microsoft",
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "scope": "https://graph.microsoft.com/Calendars.Read offline_access openid email",
        "extra_authorize": {"prompt": "select_account"},
        "capabilities": ["events.read", "event.read", "freebusy.read"],
    },
    GOOGLE: {
        "label": "Google Calendar",
        "oauth_key": "google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "scope": ("https://www.googleapis.com/auth/calendar.readonly "
                  "https://www.googleapis.com/auth/userinfo.email openid"),
        "extra_authorize": {"access_type": "offline", "prompt": "select_account consent"},
        "capabilities": ["events.read", "event.read", "freebusy.read"],
    },
}

_STATE_PREFIX = "calendar-oauth-state:"
_STATE_TTL_SECONDS = 600


def normalize_provider(provider: str) -> str | None:
    """Accept the friendly spellings a link or a legacy row might carry."""
    p = (provider or "").lower()
    if p in (MICROSOFT, "microsoft", "outlook", "office365", "ms"):
        return MICROSOFT
    if p in (GOOGLE, LEGACY_GOOGLE, "google", "gcal"):
        return GOOGLE
    return None


def is_configured(provider: str) -> bool:
    key = PROVIDERS[provider]["oauth_key"]
    return mail_oauth.is_configured(key)


def redirect_uri(provider: str) -> str:
    """Where the identity provider sends the user back.

    Deliberately **not** ``mail_oauth._redirect_uri``: that one points at
    ``/v1/email/oauth/{provider}/callback``, so borrowing it would land a
    calendar authorization on the mailbox callback, which would fail to find its
    state and leave the user staring at an error. The OAuth *client* is shared —
    same app registration, same client id — but the redirect is per flow and has
    to be registered separately in the provider console.
    """
    if provider == MICROSOFT:
        return (os.getenv("MS_GRAPH_CALENDAR_REDIRECT_URI")
                or os.getenv("MICROSOFT_CALENDAR_REDIRECT_URI", "")).strip()
    return (os.getenv("GOOGLE_CALENDAR_REDIRECT_URI")
            or os.getenv("GOOGLE_OAUTH_CALENDAR_REDIRECT_URI", "")).strip()


def _state_ref(state: str) -> str:
    return f"{_STATE_PREFIX}{state}"


def _consume_state(state: str) -> dict[str, Any] | None:
    """One-time read: the pending session is deleted whether or not it is valid."""
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


def build_authorization(
    workspace_id: str, provider: str, return_url: str | None = None
) -> dict[str, Any]:
    """The provider's consent URL, plus the pending PKCE session behind it."""
    cfg = PROVIDERS[provider]
    key = cfg["oauth_key"]
    if not mail_oauth.is_configured(key):
        return {
            "available": False,
            "provider": provider,
            "reason": f"{cfg['label']} is not configured on this deployment.",
        }

    verifier, challenge = mail_oauth._pkce_pair()  # noqa: SLF001 - shared primitive
    state = secrets.token_urlsafe(24)
    credential_store().put(_state_ref(state), {
        "workspace_id": workspace_id,
        "provider": provider,
        "verifier": verifier,
        "return_url": return_url or "",
        "expires_at": time.time() + _STATE_TTL_SECONDS,
    })

    params = {
        "response_type": "code",
        "client_id": mail_oauth._client_id(key),  # noqa: SLF001
        "scope": cfg["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        **cfg["extra_authorize"],
    }
    redirect = redirect_uri(provider)
    if redirect:
        params["redirect_uri"] = redirect
    return {
        "available": True,
        "provider": provider,
        "authorizationUrl": f"{cfg['authorize']}?{urlencode(params)}",
        "state": state,
    }


def handle_callback(session: Session, code: str, state: str) -> dict[str, Any]:
    """Exchange the code and record the connection.

    The provider comes from the stored state, not the URL: a callback that could
    be told which provider it was for would let an attacker pair a code from one
    provider with another's configuration.
    """
    pending = _consume_state(state)
    if pending is None:
        raise ValueError("authorization expired or already used")

    provider = str(pending["provider"])
    workspace_id = str(pending["workspace_id"])
    cfg = PROVIDERS[provider]
    key = cfg["oauth_key"]

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": mail_oauth._client_id(key),  # noqa: SLF001
        "code_verifier": str(pending["verifier"]),
    }
    # Must be byte-identical to the one sent at authorization time.
    redirect = redirect_uri(provider)
    if redirect:
        data["redirect_uri"] = redirect
    secret = mail_oauth._client_secret(key)  # noqa: SLF001
    if secret:
        data["client_secret"] = secret

    token = mail_oauth._token_request(key, data)  # noqa: SLF001
    account = mail_oauth._identity(key, token)  # noqa: SLF001

    row = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.provider == provider,
        )
    ).scalar_one_or_none()
    if row is None:
        row = IntegrationConnection(workspace_id=workspace_id, provider=provider)
        session.add(row)
    row.status = "connected"
    row.auth_type = "oauth"
    row.capabilities = list(cfg["capabilities"])
    # `detail` is health/identity text that is safe to show. The account address
    # is the only thing from the token that ever lands in the database.
    row.detail = account
    session.flush()

    credential_store().put(row.id, {
        "access_token": token.get("access_token", ""),
        "refresh_token": token.get("refresh_token", ""),
        "expires_at": time.time() + float(token.get("expires_in", 3600)),
        "provider": provider,
        "account": account,
    })
    return {
        "connectionId": row.id,
        "provider": provider,
        "account": account,
        "returnUrl": str(pending.get("return_url") or ""),
    }
