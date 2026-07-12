"""Persistent assistant chat sessions — models, service, and gateway API.

Verifies create/list/get/rename/delete, message append with counters and
auto-title, clear-messages (keep session), cascade delete, and workspace
isolation. These back the ChatGPT/Claude-style history in the web shell.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import ChatMessage, create_engine_from_settings, session_scope
from daypilot_orchestrator.chat import (
    append_message,
    clear_messages,
    create_session,
    delete_session,
    get_session_with_messages,
    list_sessions,
    rename_session,
)

client = TestClient(app)
ENGINE = create_engine_from_settings()


# --- service layer -----------------------------------------------------------

def test_session_lifecycle_and_autotitle():
    with session_scope() as s:
        created = create_session(s, "ws-chat-1")
        sid = created["id"]
        assert created["title"] == "New conversation"

        # First user message auto-titles the session.
        append_message(s, "ws-chat-1", sid, "user", "Which day is today and what's my plan?")
        append_message(s, "ws-chat-1", sid, "assistant", "Today is Sunday. Here is your plan.",
                       action={"kind": "navigate", "target": "planning"})

        got = get_session_with_messages(s, "ws-chat-1", sid)
        assert got["title"].startswith("Which day is today")
        assert got["messageCount"] == 2
        assert got["lastMessageAt"] is not None
        assert [m["role"] for m in got["messages"]] == ["user", "assistant"]
        assert got["messages"][1]["action"] == {"kind": "navigate", "target": "planning"}


def test_clear_keeps_session_but_drops_messages():
    with session_scope() as s:
        sid = create_session(s, "ws-chat-2")["id"]
        append_message(s, "ws-chat-2", sid, "user", "hello")
        clear_messages(s, "ws-chat-2", sid)
        got = get_session_with_messages(s, "ws-chat-2", sid)
        assert got["messageCount"] == 0
        assert got["messages"] == []


def test_delete_cascades_messages():
    with session_scope() as s:
        sid = create_session(s, "ws-chat-3")["id"]
        append_message(s, "ws-chat-3", sid, "user", "hi")
        delete_session(s, "ws-chat-3", sid)
        remaining = s.query(ChatMessage).filter(ChatMessage.session_id == sid).count()
        assert remaining == 0


def test_rename_and_workspace_isolation():
    with session_scope() as s:
        sid = create_session(s, "ws-chat-4")["id"]
        rename_session(s, "ws-chat-4", sid, "Quarterly planning")
        assert get_session_with_messages(s, "ws-chat-4", sid)["title"] == "Quarterly planning"
        # A different workspace cannot see or mutate it.
        import pytest
        with pytest.raises(KeyError):
            get_session_with_messages(s, "other-ws", sid)
        listed = list_sessions(s, "other-ws")["sessions"]
        assert all(x["id"] != sid for x in listed)


# --- gateway API -------------------------------------------------------------

def test_chat_api_end_to_end():
    ws = "ws-chat-api"
    created = client.post("/v1/chat/sessions", json={"workspaceId": ws, "title": "Kickoff"})
    assert created.status_code == 201
    sid = created.json()["id"]

    r = client.post(f"/v1/chat/sessions/{sid}/messages",
                    json={"workspaceId": ws, "role": "user", "body": "what needs approval?"})
    assert r.status_code == 201
    client.post(f"/v1/chat/sessions/{sid}/messages",
                json={"workspaceId": ws, "role": "assistant", "body": "Nothing right now."})

    got = client.get(f"/v1/chat/sessions/{sid}", params={"workspaceId": ws})
    assert got.status_code == 200
    assert got.json()["messageCount"] == 2

    listed = client.get("/v1/chat/sessions", params={"workspaceId": ws}).json()["sessions"]
    assert any(x["id"] == sid for x in listed)

    # Clear keeps the session; delete removes it.
    assert client.delete(f"/v1/chat/sessions/{sid}/messages", params={"workspaceId": ws}).status_code == 200
    assert client.get(f"/v1/chat/sessions/{sid}", params={"workspaceId": ws}).json()["messageCount"] == 0
    assert client.delete(f"/v1/chat/sessions/{sid}", params={"workspaceId": ws}).status_code == 200
    assert client.get(f"/v1/chat/sessions/{sid}", params={"workspaceId": ws}).status_code == 404


def test_missing_session_returns_404():
    assert client.get("/v1/chat/sessions/does-not-exist", params={"workspaceId": "x"}).status_code == 404
