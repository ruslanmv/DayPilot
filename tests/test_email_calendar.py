"""Tests for Email Sentinel + calendar (B9): non-destructive policy, draft-and-
approve (never auto-send), classification, and calendar conflict detection."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from daypilot_orchestrator.email.adapters.mock_adapter import MockMailAdapter
from daypilot_orchestrator.email.policy import (
    EmailAction,
    EmailActionForbidden,
    EmailApprovalRequired,
    check_action,
    is_safe,
    requires_approval,
)
from daypilot_orchestrator.email import sentinel

client = TestClient(app)


def _ws() -> str:
    return "ws-" + uuid.uuid4().hex[:8]


# --- Non-destructive policy -------------------------------------------------

def test_safe_actions_never_require_approval():
    for action in (EmailAction.READ, EmailAction.SUMMARIZE, EmailAction.DRAFT_REPLY,
                   EmailAction.CREATE_TASK, EmailAction.SAVE_DRAFT):
        assert is_safe(action)
        check_action(action)  # does not raise


def test_risky_action_requires_approval():
    assert requires_approval(EmailAction.SEND)
    with pytest.raises(EmailApprovalRequired):
        check_action(EmailAction.SEND, approved=False)
    # With approval + sending allowed by default, it passes.
    check_action(EmailAction.SEND, approved=True)


def test_destructive_actions_forbidden_by_default(monkeypatch):
    monkeypatch.delenv("DAYPILOT_EMAIL_ALLOW_DELETE", raising=False)
    with pytest.raises(EmailActionForbidden):
        check_action(EmailAction.DELETE, approved=True)
    with pytest.raises(EmailActionForbidden):
        check_action(EmailAction.EXPUNGE, approved=True)


def test_send_can_be_globally_disabled(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ALLOW_SEND", "false")
    with pytest.raises(EmailActionForbidden):
        check_action(EmailAction.SEND, approved=True)


# --- Sentinel classification ------------------------------------------------

def test_sentinel_classifies_schedule_impact_and_urgency():
    adapter = MockMailAdapter()
    alpha = adapter.fetch_message("10492")
    result = sentinel.classify(alpha)
    assert result.schedule_impact is True
    assert result.intent in {"scheduling", "request"}


def test_sentinel_drafts_reply_without_sending():
    adapter = MockMailAdapter()
    msg = adapter.fetch_message("10492")
    body = sentinel.draft_reply(msg, tone="professional")
    assert "regards" in body.lower()
    # Drafting must not mutate the inbox: still only the seeded messages.
    assert len(adapter.list_inbox()) == 3


# --- Gateway: feature flag + draft-and-approve ------------------------------

def test_email_disabled_returns_onboarding_state(monkeypatch):
    monkeypatch.delenv("DAYPILOT_EMAIL_ENABLED", raising=False)
    status = client.get("/v1/email/status").json()
    assert status["enabled"] is False and status["connected"] is False
    assert status["account"] is None
    # Onboarding providers are offered so the UI shows a real connect state.
    ids = {p["id"] for p in status["providers"]}
    assert {"microsoft", "google", "imap"} <= ids
    assert client.get("/v1/email/messages").status_code == 404


def test_oauth_start_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    r = client.post("/v1/email/oauth/yahoo/start", json={"workspaceId": _ws()})
    assert r.status_code == 400  # not silently treated as Microsoft


def test_microsoft_oauth_uses_ms_graph_env_names(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    # The documented MS_GRAPH_* names must configure Microsoft OAuth.
    monkeypatch.delenv("MICROSOFT_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "ms-client-123")
    monkeypatch.setenv("MS_GRAPH_REDIRECT_URI", "https://app.example.com/cb")
    out = client.post("/v1/email/oauth/microsoft/start", json={"workspaceId": _ws()}).json()
    assert out["available"] is True and out["provider"] == "microsoft"
    assert "ms-client-123" in out["authorizationUrl"]
    assert "app.example.com" in out["authorizationUrl"]


def test_email_status_endpoint_is_workspace_scoped():
    # Regression: the client passes workspaceId to status/folders/message.
    from pathlib import Path
    client_ts = (Path(__file__).resolve().parents[1] / "packages" / "ui-bridge" / "src"
                 / "email" / "emailClient.ts").read_text(encoding="utf-8")
    assert "'/v1/email/status?workspaceId=" in client_ts.replace('`', "'")
    assert "/v1/email/folders?workspaceId=" in client_ts
    assert "/v1/email/messages/${encodeURIComponent(uid)}?workspaceId=" in client_ts


def test_status_returns_account_and_capabilities_when_connected(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("DAYPILOT_EMAIL_ALLOW_SEND", "true")
    status = client.get("/v1/email/status").json()
    assert status["connected"] is True
    acct = status["account"]
    assert acct["provider"] == "mock" and acct["status"] == "connected"
    caps = acct["capabilities"]
    assert caps["read"] is True and caps["send"] is True and caps["drafts"] is True
    # No secrets are ever returned in the status payload.
    assert "password" not in acct and "token" not in acct


def test_message_detail_returns_real_message(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_EMAIL_PROVIDER", "mock")
    detail = client.get("/v1/email/messages/10492").json()
    assert detail["uid"] == "10492" and detail["subject"]
    assert "from" in detail and "text" in detail


def test_search_filters_messages_server_side(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_EMAIL_PROVIDER", "mock")
    ws = _ws()
    all_items = client.get(f"/v1/email/messages?workspaceId={ws}").json()["items"]
    assert all_items
    subj = all_items[0]["subject"].split()[0]
    filtered = client.get(f"/v1/email/messages?workspaceId={ws}&q={subj}").json()
    assert filtered["query"] == subj
    assert all(subj.lower() in (i["subject"] + " " + i["sender"]).lower() for i in filtered["items"])
    none = client.get(f"/v1/email/messages?workspaceId={ws}&q=zzz-no-match-zzz").json()["items"]
    assert none == []


def test_ai_revise_transforms_real_draft(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_EMAIL_PROVIDER", "mock")
    current = "Hi Anna,\n\nThank you for the update.\n\nBest regards,\nRuslan"
    revised = client.post(
        "/v1/email/ai/revise",
        json={"uid": "10492", "current": current, "instruction": "make it shorter"},
    ).json()
    assert revised["body"] and revised["body"] != current
    assert revised["instruction"] == "make it shorter"


def test_draft_and_approve_send_flow(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    monkeypatch.setenv("DAYPILOT_EMAIL_PROVIDER", "mock")
    monkeypatch.setenv("DAYPILOT_EMAIL_ALLOW_SEND", "true")
    ws = _ws()

    msgs = client.get(f"/v1/email/messages?workspaceId={ws}").json()["items"]
    assert msgs and msgs[0]["urgency"] in {"low", "medium", "high", "critical"}

    drafted = client.post(
        "/v1/email/messages/10492/draft-reply",
        json={"uid": "10492", "workspaceId": ws},
    ).json()
    assert drafted["requiresApproval"] is True
    draft_uid = drafted["draftUid"]

    # Sending without the visible approval payload is refused (403).
    blocked = client.post(
        "/v1/email/drafts/send",
        json={"draftUid": draft_uid, "to": ["pm@clientalpha.com"], "subject": "Re: x",
              "text": "hi", "workspaceId": ws, "approval": {"confirmed_by_user": False}},
    )
    assert blocked.status_code == 403


def test_create_task_from_email(monkeypatch):
    monkeypatch.setenv("DAYPILOT_EMAIL_ENABLED", "true")
    ws = _ws()
    resp = client.post(
        "/v1/email/messages/10492/create-task",
        json={"uid": "10492", "title": "Reply to Client Alpha", "workspaceId": ws},
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Reply to Client Alpha"


# --- Calendar ---------------------------------------------------------------

def test_calendar_detects_overlapping_events():
    ws = _ws()
    # Syncing is an explicit POST now: reading the calendar used to perform the
    # upsert as a side effect, which made rendering it a write.
    assert client.post(f"/v1/calendar/sync?workspaceId={ws}").json()["synced"] == 3
    body = client.get(f"/v1/calendar/events?workspaceId={ws}").json()
    assert len(body["items"]) == 3
    # The seeded 09:00-10:00 and 09:30-11:00 events overlap.
    assert len(body["conflicts"]) >= 1


def test_calendar_event_draft_is_approval_gated():
    ws = _ws()
    resp = client.post(
        "/v1/calendar/events/draft",
        json={"title": "Review block", "startAt": "2026-07-10T15:30:00",
              "endAt": "2026-07-10T16:00:00", "workspaceId": ws},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["approvalStatus"] == "pending"
