"""Tests for backend-owned mailbox connections (Batch 3).

The mail setup wizard drives a real, non-destructive IMAP/SMTP probe, persists a
connection only after a successful probe, keeps secrets out of every response,
and reports honest error codes. No live mail server is required — probes against
unreachable hosts exercise the real error-mapping path.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app import mail_setup
from daypilot_knowledge.db import MailboxConnection, session_scope
from daypilot_orchestrator.email.adapters.unconfigured_adapter import UnconfiguredMailAdapter

client = TestClient(app)


def _ws() -> str:
    return "mail-" + uuid.uuid4().hex[:8]


def _enable(monkeypatch) -> None:
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.delenv("DAYPILOT_EMAIL_PROVIDER", raising=False)


# --- status / onboarding -----------------------------------------------------

def test_status_shows_onboarding_when_no_mailbox(monkeypatch):
    _enable(monkeypatch)
    body = client.get(f"/v1/email/status?workspaceId={_ws()}").json()
    assert body["enabled"] is True
    assert body["connected"] is False
    assert body["account"] is None
    ids = {p["id"] for p in body["providers"]}
    assert {"google", "microsoft", "imap"} <= ids


# --- non-destructive probe: honest error codes ------------------------------

def test_probe_missing_host_and_credentials():
    out = mail_setup.probe("imap", {"imapHost": ""}, "user@x.com", "pw")
    assert out["code"] == "missing_host"
    out = mail_setup.probe("imap", {"imapHost": "imap.example.com"}, "", "")
    assert out["code"] == "missing_credentials"


def test_test_endpoint_reports_connection_refused(monkeypatch):
    _enable(monkeypatch)
    ws = _ws()
    # Nothing listens on 127.0.0.1:1 → a real connection-refused, not a fake OK.
    resp = client.post("/v1/email/test", json={
        "provider": "imap", "workspaceId": ws,
        "emailAddress": "user@example.com", "username": "user@example.com", "password": "secret",
        "imapHost": "127.0.0.1", "imapPort": 1, "imapSecurity": "starttls",
    })
    assert resp.status_code == 200
    assert resp.json()["code"] in ("connection_refused", "timeout", "imap_error", "tls_error")


def test_test_endpoint_reports_dns_error(monkeypatch):
    _enable(monkeypatch)
    resp = client.post("/v1/email/test", json={
        "provider": "imap", "workspaceId": _ws(),
        "emailAddress": "user@example.com", "username": "user@example.com", "password": "secret",
        "imapHost": "no-such-host.invalid", "imapPort": 993, "imapSecurity": "ssl",
    })
    assert resp.json()["code"] in ("dns_error", "timeout")


# --- connect only persists on success; never leaks secrets -------------------

def test_connect_failure_does_not_persist_connected(monkeypatch):
    _enable(monkeypatch)
    ws = _ws()
    resp = client.post("/v1/email/connect", json={
        "provider": "imap", "workspaceId": ws,
        "emailAddress": "user@example.com", "username": "user@example.com", "password": "secret",
        "imapHost": "127.0.0.1", "imapPort": 1, "imapSecurity": "starttls",
    })
    assert resp.status_code == 200
    assert resp.json()["code"] != "connected"
    # A failed probe never yields a connected mailbox.
    status = client.get(f"/v1/email/status?workspaceId={ws}").json()
    assert status["connected"] is False


def test_status_and_connection_never_return_secrets(monkeypatch):
    _enable(monkeypatch)
    ws = _ws()
    client.post("/v1/email/test", json={
        "provider": "imap", "workspaceId": ws,
        "username": "user@example.com", "password": "top-secret-pw",
        "imapHost": "127.0.0.1", "imapPort": 1,
    })
    raw = client.get(f"/v1/email/status?workspaceId={ws}").text
    assert "top-secret-pw" not in raw
    assert "secretReference" not in raw and "secret_reference" not in raw


# --- disconnect resets to unconfigured --------------------------------------

def test_disconnect_resets_connection(monkeypatch):
    _enable(monkeypatch)
    ws = _ws()
    # Seed a "connected" row directly, as a successful probe would.
    with session_scope() as s:
        s.add(MailboxConnection(
            workspace_id=ws, provider="imap", email_address="u@x.com",
            status="connected", secret_reference=f"mailbox:{ws}",
        ))
    from daypilot_orchestrator.integrations.credentials import credential_store
    credential_store().put(f"mailbox:{ws}", {"password": "pw", "username": "u@x.com"})

    status = client.get(f"/v1/email/status?workspaceId={ws}").json()
    assert status["connected"] is True

    out = client.post("/v1/email/disconnect", json={"workspaceId": ws}).json()
    assert out["disconnected"] is True
    assert out["connection"]["status"] == "unconfigured"
    assert credential_store().has(f"mailbox:{ws}") is False


# --- adapter selection is honest --------------------------------------------

def test_adapter_is_unconfigured_when_not_connected():
    with session_scope() as s:
        adapter = mail_setup.adapter_for_workspace(s, _ws())
    assert isinstance(adapter, UnconfiguredMailAdapter)
    assert adapter.list_inbox() == []


# --- OAuth start is honest when not configured -------------------------------

def test_oauth_start_is_honest_without_client_credentials(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    out = client.post("/v1/email/oauth/google/start", json={"workspaceId": _ws()}).json()
    assert out["available"] is False
    assert out["fallback"] == "imap"


def test_oauth_start_returns_authorization_url_when_configured(monkeypatch):
    """Configured OAuth returns a real provider authorization URL to redirect to,
    with client id + CSRF state bound to the workspace (authorization-code flow)."""
    _enable(monkeypatch)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "goog-client-123")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://app.example.com/mail/oauth/callback")
    ws = _ws()
    out = client.post("/v1/email/oauth/google/start", json={"workspaceId": ws}).json()
    assert out["available"] is True
    assert out["authorizationUrl"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=goog-client-123" in out["authorizationUrl"]
    assert "response_type=code" in out["authorizationUrl"]
    assert "redirect_uri=" in out["authorizationUrl"]
    # Authorization-code flow with PKCE; the workspace is bound to the state
    # server-side (not embedded in the opaque state token).
    assert "code_challenge=" in out["authorizationUrl"]
    assert "code_challenge_method=S256" in out["authorizationUrl"]
    assert out["state"]


def test_discover_resolves_known_domain_and_flags_unknown(monkeypatch):
    _enable(monkeypatch)
    found = client.post("/v1/email/discover", json={"emailAddress": "alex@fastmail.com"}).json()
    assert found["status"] == "found"
    assert found["settings"]["imapHost"] == "imap.fastmail.com"
    # Fastmail's secure submission is 465/SSL — not the generic 587/STARTTLS default.
    assert found["settings"]["smtpPort"] == 465 and found["settings"]["smtpSecurity"] == "ssl"
    assert found["appPasswordRecommended"] is True
    unknown = client.post("/v1/email/discover", json={"emailAddress": "person@some-corp.example"}).json()
    assert unknown["status"] == "manual_required"


def test_connect_resolves_hosts_from_domain_without_manual_entry(monkeypatch):
    """A generic account can connect with only email + password: the backend
    discovers the domain's hosts before probing (no imapHost supplied)."""
    _enable(monkeypatch)
    seen: dict = {}

    def fake_probe(provider, cfg, username, password):
        seen["hosts"] = mail_setup._resolve_hosts(provider, cfg)
        return {"code": "connected", "checks": {"imap": "ok", "smtp": "ok"}, "hosts": seen["hosts"]}

    monkeypatch.setattr(mail_setup, "probe", fake_probe)
    ws = _ws()
    out = client.post("/v1/email/connect", json={
        "provider": "imap", "workspaceId": ws,
        "emailAddress": "someone@fastmail.com", "password": "app-pw-here",
    }).json()
    assert out["code"] == "connected"
    assert seen["hosts"]["imap_host"] == "imap.fastmail.com"  # discovered, not typed
    assert seen["hosts"]["smtp_port"] == 465
