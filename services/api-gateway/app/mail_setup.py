"""Backend-owned mailbox connections (Batch 3).

The backend is the source of truth for mail connection state — the browser never
infers a mailbox from local state. A connection is only marked `connected` after
a real IMAP/SMTP probe succeeds. Passwords and OAuth tokens are held by the
credential store (secret-by-reference) and are never returned to the browser or
written to logs. The probe is strictly non-destructive: it opens the INBOX
read-only (never marking messages read) and speaks EHLO/STARTTLS to SMTP without
ever issuing a MAIL FROM — it never sends.

State machine (per connection):
    unconfigured | testing | connected | degraded | unauthorized | offline
"""
from __future__ import annotations

import imaplib
import os
import secrets
import smtplib
import socket
import ssl
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import MailboxConnection
from daypilot_knowledge.db.models import utcnow
from daypilot_orchestrator.integrations.credentials import credential_store

# Providers the onboarding wizard can offer. gmail/microsoft ride OAuth in a real
# deployment; imap is available wherever the user supplies host + credentials.
PROVIDERS = [
    {"id": "google", "label": "Gmail", "auth": "oauth"},
    {"id": "microsoft", "label": "Microsoft 365", "auth": "oauth"},
    {"id": "imap", "label": "Other email provider (IMAP/SMTP)", "auth": "password"},
]

# Well-known hosts so IMAP/SMTP for the big providers can be pre-filled.
_PROVIDER_HOSTS = {
    "google": ("imap.gmail.com", 993, "ssl", "smtp.gmail.com", 587, "starttls"),
    "gmail": ("imap.gmail.com", 993, "ssl", "smtp.gmail.com", 587, "starttls"),
    "microsoft": ("outlook.office365.com", 993, "ssl", "smtp.office365.com", 587, "starttls"),
}

# Domain → (imap_host, imap_port, imap_security, smtp_host, smtp_port, smtp_security,
# app_password_recommended). An internal implementation detail: the user only ever
# sees "settings discovered automatically". Both secure SMTP shapes are represented —
# 465+SSL and 587+STARTTLS — rather than assuming 587/STARTTLS for every domain.
_GMAIL = ("imap.gmail.com", 993, "ssl", "smtp.gmail.com", 587, "starttls", True)
_MS = ("outlook.office365.com", 993, "ssl", "smtp.office365.com", 587, "starttls", True)
_ICLOUD = ("imap.mail.me.com", 993, "ssl", "smtp.mail.me.com", 587, "starttls", True)
_YAHOO = ("imap.mail.yahoo.com", 993, "ssl", "smtp.mail.yahoo.com", 465, "ssl", True)
_AOL = ("imap.aol.com", 993, "ssl", "smtp.aol.com", 465, "ssl", True)
_FASTMAIL = ("imap.fastmail.com", 993, "ssl", "smtp.fastmail.com", 465, "ssl", True)
_GMX = ("imap.gmx.com", 993, "ssl", "mail.gmx.com", 587, "starttls", False)
_ZOHO = ("imap.zoho.com", 993, "ssl", "smtp.zoho.com", 465, "ssl", False)
DOMAIN_PRESETS: dict[str, tuple] = {
    "gmail.com": _GMAIL, "googlemail.com": _GMAIL,
    "outlook.com": _MS, "hotmail.com": _MS, "live.com": _MS, "msn.com": _MS, "office365.com": _MS,
    "icloud.com": _ICLOUD, "me.com": _ICLOUD, "mac.com": _ICLOUD,
    "yahoo.com": _YAHOO, "ymail.com": _YAHOO, "yahoo.co.uk": _YAHOO,
    "aol.com": _AOL,
    "fastmail.com": _FASTMAIL, "fastmail.fm": _FASTMAIL,
    "gmx.com": _GMX, "gmx.net": _GMX,
    "zoho.com": _ZOHO,
}

_PROBE_TIMEOUT = 8.0


def discover_mailbox(email_address: str) -> dict[str, Any]:
    """Resolve IMAP/SMTP settings from an email domain, so the user never types a
    server. ``status`` is 'found' for a known domain, otherwise 'manual_required'
    (a best-guess is still returned so Advanced settings can be pre-filled). The
    hostname is never *presented* as confirmed until a probe verifies it."""
    email = (email_address or "").strip().lower()
    if "@" not in email:
        return {"status": "manual_required"}
    domain = email.rsplit("@", 1)[1]
    preset = DOMAIN_PRESETS.get(domain)
    if preset:
        ih, ip, isec, sh, sp, ssec, apr = preset
        return {
            "status": "found", "username": email, "appPasswordRecommended": apr,
            "settings": {
                "imapHost": ih, "imapPort": ip, "imapSecurity": isec,
                "smtpHost": sh, "smtpPort": sp, "smtpSecurity": ssec,
            },
        }
    # Unknown domain: return a conventional guess (unverified) for Advanced to show.
    return {
        "status": "manual_required", "username": email, "appPasswordRecommended": False,
        "settings": {
            "imapHost": f"imap.{domain}", "imapPort": 993, "imapSecurity": "ssl",
            "smtpHost": f"smtp.{domain}", "smtpPort": 587, "smtpSecurity": "starttls",
        },
    }


# ---- persistence helpers ----------------------------------------------------

def _get(session: Session, workspace_id: str) -> MailboxConnection | None:
    return session.execute(
        select(MailboxConnection).where(MailboxConnection.workspace_id == workspace_id)
    ).scalar_one_or_none()


def _public(row: MailboxConnection | None) -> dict[str, Any] | None:
    """Safe view — never includes secrets."""
    if row is None:
        return None
    return {
        "id": row.id,
        "provider": row.provider,
        "emailAddress": row.email_address,
        "displayName": row.display_name,
        "imapHost": row.imap_host,
        "imapPort": row.imap_port,
        "imapSecurity": row.imap_security,
        "smtpHost": row.smtp_host,
        "smtpPort": row.smtp_port,
        "smtpSecurity": row.smtp_security,
        "status": row.status,
        "lastTestedAt": row.last_tested_at.isoformat() if row.last_tested_at else None,
        "lastErrorCode": row.last_error_code,
    }


def mailbox_status(session: Session, workspace_id: str) -> dict[str, Any]:
    """Real mailbox status. Always reachable — when nothing is connected the UI
    shows the connect-your-email onboarding rather than fabricated data."""
    row = _get(session, workspace_id)
    connected = row is not None and row.status == "connected"
    return {
        "connected": connected,
        "connection": _public(row),
        "providers": PROVIDERS,
    }


# ---- the non-destructive probe ---------------------------------------------

def _resolve_hosts(provider: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Fill IMAP/SMTP hosts from the well-known table for gmail/microsoft, else
    take the user-supplied values verbatim."""
    if provider in _PROVIDER_HOSTS:
        ih, ip, isec, sh, sp, ssec = _PROVIDER_HOSTS[provider]
        return {
            "imap_host": ih, "imap_port": ip, "imap_security": isec,
            "smtp_host": sh, "smtp_port": sp, "smtp_security": ssec,
        }
    # No manual host supplied → discover from the email domain, so a generic
    # account can connect with just an address + password.
    if not (cfg.get("imapHost") or "").strip():
        disc = discover_mailbox(cfg.get("emailAddress") or cfg.get("username") or "")
        s = disc.get("settings")
        if s:
            return {
                "imap_host": s["imapHost"], "imap_port": s["imapPort"], "imap_security": s["imapSecurity"],
                "smtp_host": s["smtpHost"], "smtp_port": s["smtpPort"], "smtp_security": s["smtpSecurity"],
            }
    return {
        "imap_host": (cfg.get("imapHost") or "").strip(),
        "imap_port": int(cfg.get("imapPort") or 993),
        "imap_security": cfg.get("imapSecurity") or "ssl",
        "smtp_host": (cfg.get("smtpHost") or cfg.get("imapHost") or "").strip(),
        "smtp_port": int(cfg.get("smtpPort") or 587),
        "smtp_security": cfg.get("smtpSecurity") or "starttls",
    }


def _probe_imap(host: str, port: int, security: str, username: str, password: str) -> str | None:
    """Return an error code, or None on success. Opens INBOX read-only — never
    marks a message read, never deletes, never sends."""
    client: imaplib.IMAP4 | None = None
    try:
        ctx = ssl.create_default_context()
        if security == "ssl":
            client = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=_PROBE_TIMEOUT)
        else:
            client = imaplib.IMAP4(host, port, timeout=_PROBE_TIMEOUT)
            if security == "starttls":
                client.starttls(ssl_context=ctx)
        try:
            typ, _ = client.login(username, password)
        except imaplib.IMAP4.error:
            return "imap_auth_failed"
        if typ != "OK":
            return "imap_auth_failed"
        # read-only SELECT — cannot change flags or delete
        typ, _ = client.select("INBOX", readonly=True)
        if typ != "OK":
            return "imap_select_failed"
        return None
    except socket.gaierror:
        return "dns_error"
    except ssl.SSLError:
        return "tls_error"
    except (ConnectionRefusedError, OSError) as exc:
        if isinstance(exc, socket.timeout) or "timed out" in str(exc).lower():
            return "timeout"
        if isinstance(exc, ConnectionRefusedError):
            return "connection_refused"
        return "imap_error"
    except imaplib.IMAP4.error:
        return "imap_error"
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


def _probe_smtp(host: str, port: int, security: str, username: str, password: str) -> str | None:
    """Return an error code, or None on success. Authenticates only — issues
    EHLO/STARTTLS and AUTH, never MAIL FROM, so nothing is ever sent."""
    server: smtplib.SMTP | None = None
    try:
        ctx = ssl.create_default_context()
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=_PROBE_TIMEOUT, context=ctx)
        else:
            server = smtplib.SMTP(host, port, timeout=_PROBE_TIMEOUT)
            server.ehlo()
            if security == "starttls":
                server.starttls(context=ctx)
                server.ehlo()
        try:
            server.login(username, password)
        except smtplib.SMTPAuthenticationError:
            return "smtp_auth_failed"
        return None
    except socket.gaierror:
        return "dns_error"
    except ssl.SSLError:
        return "tls_error"
    except smtplib.SMTPException:
        return "smtp_error"
    except (ConnectionRefusedError, OSError) as exc:
        if isinstance(exc, socket.timeout) or "timed out" in str(exc).lower():
            return "timeout"
        if isinstance(exc, ConnectionRefusedError):
            return "connection_refused"
        return "smtp_error"
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


def probe(provider: str, cfg: dict[str, Any], username: str, password: str) -> dict[str, Any]:
    """Run the full non-destructive probe. Returns {code, checks:{imap,smtp}}."""
    hosts = _resolve_hosts(provider, cfg)
    if not hosts["imap_host"]:
        return {"code": "missing_host", "checks": {}}
    if not username or not password:
        return {"code": "missing_credentials", "checks": {}}

    imap_err = _probe_imap(
        hosts["imap_host"], hosts["imap_port"], hosts["imap_security"], username, password
    )
    checks: dict[str, str] = {"imap": "ok" if imap_err is None else imap_err}
    if imap_err is not None:
        return {"code": imap_err, "checks": checks, "hosts": hosts}

    smtp_err = _probe_smtp(
        hosts["smtp_host"], hosts["smtp_port"], hosts["smtp_security"], username, password
    )
    checks["smtp"] = "ok" if smtp_err is None else smtp_err
    if smtp_err is not None:
        # IMAP works but SMTP doesn't — reads are fine, sending would fail.
        return {"code": smtp_err, "checks": checks, "hosts": hosts, "degraded": True}

    return {"code": "connected", "checks": checks, "hosts": hosts}


# ---- test / connect / disconnect / reconnect --------------------------------

def _upsert(session: Session, workspace_id: str, provider: str) -> MailboxConnection:
    row = _get(session, workspace_id)
    if row is None:
        row = MailboxConnection(workspace_id=workspace_id, provider=provider)
        session.add(row)
        session.flush()
    else:
        row.provider = provider
    return row


def test_mailbox(session: Session, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Probe a candidate mailbox without persisting credentials or flipping the
    connection to connected. Records only the test outcome + timestamp."""
    provider = (body.get("provider") or "imap").lower()
    username = (body.get("username") or body.get("emailAddress") or "").strip()
    password = body.get("password") or ""
    result = probe(provider, body, username, password)
    row = _upsert(session, workspace_id, provider)
    row.last_tested_at = utcnow()
    row.last_error_code = None if result["code"] == "connected" else result["code"]
    # Testing never advances a fresh mailbox to connected — connect does that.
    if row.status not in ("connected",):
        row.status = "testing" if result["code"] == "connected" else "offline"
    session.flush()
    return {
        "code": result["code"],
        "checks": result.get("checks", {}),
        "degraded": result.get("degraded", False),
    }


def connect_mailbox(session: Session, workspace_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Probe, and only on success persist the connection + store the secret by
    reference. Reads/sends stay governed by the existing email policy."""
    provider = (body.get("provider") or "imap").lower()
    username = (body.get("username") or body.get("emailAddress") or "").strip()
    password = body.get("password") or ""
    result = probe(provider, body, username, password)
    if result["code"] not in ("connected",) and not result.get("degraded"):
        # Do not persist a non-working connection.
        row = _upsert(session, workspace_id, provider)
        row.last_tested_at = utcnow()
        row.last_error_code = result["code"]
        row.status = "offline"
        session.flush()
        return {"code": result["code"], "checks": result.get("checks", {})}

    hosts = result.get("hosts", _resolve_hosts(provider, body))
    row = _upsert(session, workspace_id, provider)
    row.email_address = (body.get("emailAddress") or username or "").strip()
    row.display_name = body.get("displayName") or None
    row.username = username
    row.imap_host = hosts["imap_host"]
    row.imap_port = hosts["imap_port"]
    row.imap_security = hosts["imap_security"]
    row.smtp_host = hosts["smtp_host"]
    row.smtp_port = hosts["smtp_port"]
    row.smtp_security = hosts["smtp_security"]
    row.last_tested_at = utcnow()
    row.last_error_code = None if result["code"] == "connected" else result["code"]
    row.status = "connected" if result["code"] == "connected" else "degraded"

    ref = f"mailbox:{row.id}"
    credential_store().put(ref, {"password": password, "username": username})
    row.secret_reference = ref
    session.flush()
    return {"code": result["code"], "connection": _public(row), "degraded": result.get("degraded", False)}


def disconnect(session: Session, workspace_id: str) -> dict[str, Any]:
    """Forget the mailbox: delete the secret and reset to unconfigured."""
    row = _get(session, workspace_id)
    if row is None:
        return {"disconnected": True, "connection": None}
    if row.secret_reference:
        credential_store().delete(row.secret_reference)
    row.secret_reference = None
    row.status = "unconfigured"
    row.last_error_code = None
    session.flush()
    return {"disconnected": True, "connection": _public(row)}


def reconnect(session: Session, workspace_id: str) -> dict[str, Any]:
    """Re-probe the stored mailbox using the stored secret (no re-entry needed)."""
    row = _get(session, workspace_id)
    if row is None or not row.secret_reference:
        return {"code": "not_configured", "connection": _public(row)}
    secret = credential_store().get(row.secret_reference)
    cfg = {
        "imapHost": row.imap_host, "imapPort": row.imap_port, "imapSecurity": row.imap_security,
        "smtpHost": row.smtp_host, "smtpPort": row.smtp_port, "smtpSecurity": row.smtp_security,
    }
    result = probe(row.provider, cfg, secret.get("username", ""), secret.get("password", ""))
    row.last_tested_at = utcnow()
    row.last_error_code = None if result["code"] == "connected" else result["code"]
    row.status = "connected" if result["code"] == "connected" else (
        "degraded" if result.get("degraded") else "offline"
    )
    session.flush()
    return {"code": result["code"], "connection": _public(row), "checks": result.get("checks", {})}


def adapter_for_workspace(session: Session, workspace_id: str):
    """Return the live mailbox adapter for a workspace.

    Real connection → a configured IMAP/SMTP adapter built from stored, safe
    metadata + the credential-store secret. No connection → the Unconfigured
    adapter (empty reads, refusing writes). The Mock adapter is only used when
    the deployment explicitly opts into demo mode, never as a silent fallback.
    """
    from daypilot_orchestrator.email.adapters.imap_smtp_adapter import (
        ImapSmtpAdapter,
        ImapSmtpConfig,
    )
    from daypilot_orchestrator.email.adapters.mock_adapter import MockMailAdapter
    from daypilot_orchestrator.email.adapters.unconfigured_adapter import (
        UnconfiguredMailAdapter,
    )

    if os.getenv("DAYPILOT_EMAIL_PROVIDER", "").lower() == "mock":
        return MockMailAdapter()

    row = _get(session, workspace_id)
    if row is None or row.status not in ("connected", "degraded") or not row.secret_reference:
        return UnconfiguredMailAdapter()
    secret = credential_store().get(row.secret_reference)
    return ImapSmtpAdapter(
        ImapSmtpConfig(
            imap_host=row.imap_host or "",
            imap_port=row.imap_port,
            smtp_host=row.smtp_host or row.imap_host or "",
            smtp_port=row.smtp_port,
            username=secret.get("username", row.username or ""),
            password=secret.get("password", ""),
            use_tls=(row.imap_security in ("ssl", "starttls")),
        )
    )


# OAuth authorize endpoints + the IMAP/SMTP scopes DayPilot needs (XOAUTH2).
_OAUTH_AUTHORIZE = {
    "google": (
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://mail.google.com/ https://www.googleapis.com/auth/userinfo.email",
    ),
    "microsoft": (
        "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "https://outlook.office.com/IMAP.AccessAsUser.All "
        "https://outlook.office.com/SMTP.Send offline_access openid email",
    ),
}


def oauth_start(session: Session, workspace_id: str, provider: str) -> dict[str, Any]:
    """OAuth for Gmail/Microsoft. Honest: only available when the deployment has
    configured OAuth client credentials. When configured, returns the real
    provider authorization URL the browser redirects to (authorization-code flow,
    with a CSRF ``state`` bound to the workspace). Otherwise the UI falls back to
    an app password over IMAP/SMTP rather than pretending a flow exists."""
    provider = provider.lower()
    key = "google" if provider in ("google", "gmail") else "microsoft"
    env_prefix = "GOOGLE" if key == "google" else "MICROSOFT"
    client_id = os.getenv(f"{env_prefix}_OAUTH_CLIENT_ID", "")
    if not client_id:
        return {
            "available": False,
            "reason": "oauth_not_configured",
            "fallback": "imap",
            "message": (
                f"{key.title()} secure sign-in isn't configured on this deployment. "
                "Connect using an app password instead."
            ),
        }
    authorize_base, scope = _OAUTH_AUTHORIZE[key]
    state = f"{workspace_id}:{secrets.token_urlsafe(16)}"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": scope,
        "state": state,
        "access_type": "offline",   # Google: return a refresh token
        "prompt": "select_account consent",
    }
    redirect_uri = os.getenv(f"{env_prefix}_OAUTH_REDIRECT_URI", "").strip()
    if redirect_uri:
        params["redirect_uri"] = redirect_uri
    return {
        "available": True,
        "provider": key,
        "authorizationUrl": f"{authorize_base}?{urlencode(params)}",
        "state": state,
    }
