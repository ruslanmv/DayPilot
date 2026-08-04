"""Gmail / Microsoft mailbox OAuth — authorization-code + PKCE + XOAUTH2 (R5).

Exercises the full server-side flow with a mocked provider (httpx.MockTransport):
start returns an authorization URL with PKCE + a one-time state; the callback
exchanges the code, fetches the identity, stores tokens server-side, and marks
the mailbox connected; expired access tokens refresh; and the adapter speaks
SASL XOAUTH2 (not LOGIN with a token as the password).
"""
from __future__ import annotations

import base64
import json
import time
import uuid

import httpx
from fastapi.testclient import TestClient

from app import mail_oauth
from app.main import app
from daypilot_knowledge.db import MailboxConnection, session_scope
from daypilot_orchestrator.integrations.credentials import credential_store

client = TestClient(app)


def _ws() -> str:
    return "mail-oauth-" + uuid.uuid4().hex[:8]


def _id_token(email: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"{header}.{claims}.sig"


def _google_transport(email: str, calls: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            body = dict(x.split("=", 1) for x in request.content.decode().split("&") if "=" in x)
            calls["token_body"] = body
            return httpx.Response(200, json={
                "access_token": "at-fresh", "refresh_token": "rt-1",
                "id_token": _id_token(email), "expires_in": 3600, "token_type": "Bearer",
            })
        if "userinfo" in path:
            calls["userinfo_auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"email": email})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_oauth_start_returns_pkce_authorization_url(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "gc-123")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://app.example.com/v1/email/oauth/google/callback")
    r = client.post("/v1/email/oauth/google/start", json={"workspaceId": _ws()})
    data = r.json()
    assert data["available"] is True
    assert "code_challenge=" in data["authorizationUrl"]
    assert "code_challenge_method=S256" in data["authorizationUrl"]
    assert "gc-123" in data["authorizationUrl"] and data["state"]


def test_oauth_callback_connects_mailbox_and_stores_tokens(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "gc-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "gsecret")
    ws = _ws()
    start = client.post("/v1/email/oauth/google/start", json={"workspaceId": ws}).json()
    state = start["state"]

    calls: dict = {}
    mail_oauth.set_transport(_google_transport("jane@gmail.com", calls))
    try:
        r = client.get(f"/v1/email/oauth/google/callback?code=auth-code-1&state={state}",
                       follow_redirects=False)
    finally:
        mail_oauth.set_transport(None)

    assert r.status_code == 303
    assert "email=connected" in r.headers["location"]
    # PKCE verifier was sent on the token exchange; identity used the access token.
    assert "code_verifier" in calls["token_body"]
    assert calls["userinfo_auth"] == "Bearer at-fresh"

    with session_scope() as s:
        row = s.execute(
            MailboxConnection.__table__.select().where(MailboxConnection.workspace_id == ws)
        ).first()
        assert row is not None
    # The mailbox is connected as the identified account; tokens are server-side.
    with session_scope() as s:
        conn = s.query(MailboxConnection).filter_by(workspace_id=ws).one()
        assert conn.status == "connected" and conn.email_address == "jane@gmail.com"
        assert conn.provider == "google" and conn.imap_host == "imap.gmail.com"
        secret = credential_store().get(conn.secret_reference)
        assert secret["auth"] == "xoauth2" and secret["access_token"] == "at-fresh"
        assert secret["refresh_token"] == "rt-1"


def test_oauth_callback_rejects_unknown_state(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    r = client.get("/v1/email/oauth/google/callback?code=x&state=not-a-real-state",
                   follow_redirects=False)
    assert r.status_code == 303 and "email=error" in r.headers["location"]
    assert "invalid_state" in r.headers["location"]


def test_state_is_one_time(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "gc-123")
    out = mail_oauth.build_authorization(_ws(), "google")
    state = out["state"]
    assert mail_oauth._consume_state(state) is not None
    assert mail_oauth._consume_state(state) is None  # consumed → gone


def test_xoauth2_credentials_refreshes_expired_token(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "gc-123")
    ws = _ws()
    with session_scope() as s:
        row = MailboxConnection(workspace_id=ws, provider="google", email_address="jane@gmail.com",
                                secret_reference=f"mailbox:{uuid.uuid4().hex}", status="connected")
        s.add(row)
        s.flush()
        ref, rid = row.secret_reference, row.id
    credential_store().put(ref, {
        "auth": "xoauth2", "provider": "google", "email": "jane@gmail.com",
        "access_token": "at-old", "refresh_token": "rt-1", "expires_at": time.time() - 10,  # expired
    })

    calls: dict = {}
    mail_oauth.set_transport(_google_transport("jane@gmail.com", calls))
    try:
        with session_scope() as s:
            row = s.query(MailboxConnection).filter_by(id=rid).one()
            creds = mail_oauth.xoauth2_credentials(s, row)
    finally:
        mail_oauth.set_transport(None)

    assert creds == ("jane@gmail.com", "at-fresh")  # refreshed
    assert calls["token_body"].get("grant_type") == "refresh_token"


def test_xoauth2_sasl_string_format():
    from daypilot_orchestrator.email.adapters.imap_smtp_adapter import xoauth2_string
    s = xoauth2_string("jane@gmail.com", "at-123")
    assert s == "user=jane@gmail.com\x01auth=Bearer at-123\x01\x01"


def test_adapter_for_workspace_uses_xoauth2_with_refreshed_token(monkeypatch):
    """The live read/send adapter for a connected OAuth mailbox speaks XOAUTH2
    with a fresh access token — refreshing an expired one — never a password."""
    from app import mail_setup
    from daypilot_orchestrator.email.adapters.imap_smtp_adapter import ImapSmtpAdapter

    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "gc-123")
    ws = _ws()
    with session_scope() as s:
        row = MailboxConnection(
            workspace_id=ws, provider="google", email_address="jane@gmail.com",
            imap_host="imap.gmail.com", imap_port=993,
            smtp_host="smtp.gmail.com", smtp_port=465, imap_security="ssl",
            secret_reference=f"mailbox:{uuid.uuid4().hex}", status="connected",
        )
        s.add(row)
    credential_store().put(row.secret_reference, {
        "auth": "xoauth2", "provider": "google", "email": "jane@gmail.com",
        "access_token": "at-old", "refresh_token": "rt-1", "expires_at": time.time() - 10,  # expired
    })

    mail_oauth.set_transport(_google_transport("jane@gmail.com", {}))
    try:
        with session_scope() as s:
            adapter = mail_setup.adapter_for_workspace(s, ws)
    finally:
        mail_oauth.set_transport(None)

    assert isinstance(adapter, ImapSmtpAdapter)
    assert adapter.cfg.auth == "xoauth2"
    assert adapter.cfg.password == "at-fresh"  # refreshed access token, not a password
    assert adapter.cfg.username == "jane@gmail.com"
    assert adapter.cfg.imap_host == "imap.gmail.com" and adapter.cfg.smtp_host == "smtp.gmail.com"
