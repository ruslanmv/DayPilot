"""Persistent assistant chat sessions (ChatGPT / Claude-style history)."""
from .service import (
    append_message,
    clear_messages,
    create_session,
    delete_session,
    get_session_with_messages,
    list_sessions,
    rename_session,
)

__all__ = [
    "append_message",
    "clear_messages",
    "create_session",
    "delete_session",
    "get_session_with_messages",
    "list_sessions",
    "rename_session",
]
