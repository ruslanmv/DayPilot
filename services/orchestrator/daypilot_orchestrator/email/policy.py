"""Non-destructive email policy (batch B9).

DayPilot must never behave like an aggressive mail client. Reads, summaries,
classification, and local task/draft creation are always safe. Anything that
mutates the mailbox or sends is either forbidden by default or requires an
explicit, visible approval — enforced here, not in the UI.
"""
from __future__ import annotations

import os
from enum import StrEnum


class EmailAction(StrEnum):
    # Always-safe (read-only or local-only).
    READ = "read"
    SUMMARIZE = "summarize"
    CLASSIFY = "classify"
    CREATE_TASK = "create_task"
    CREATE_NOTE = "create_note"
    DRAFT_REPLY = "draft_reply"
    SAVE_DRAFT = "save_draft"
    ADD_LOCAL_LABEL = "add_local_label"
    SUGGEST_ARCHIVE = "suggest_archive"
    SUGGEST_FOLLOWUP = "suggest_followup"
    # Risky (mailbox mutation / send / egress) — require approval.
    SEND = "send"
    ARCHIVE = "archive"
    MOVE = "move"
    MARK_READ = "mark_read"
    APPLY_SERVER_LABEL = "apply_server_label"
    FORWARD_EXTERNAL = "forward_external"
    DOWNLOAD_ATTACHMENT = "download_attachment"
    SHARE_WITH_AGENT = "share_with_agent"
    # Forbidden by default (destructive) — never performed without an explicit
    # allow flag AND approval.
    DELETE = "delete"
    EXPUNGE = "expunge"


SAFE_ACTIONS = frozenset(
    {
        EmailAction.READ, EmailAction.SUMMARIZE, EmailAction.CLASSIFY,
        EmailAction.CREATE_TASK, EmailAction.CREATE_NOTE, EmailAction.DRAFT_REPLY,
        EmailAction.SAVE_DRAFT, EmailAction.ADD_LOCAL_LABEL,
        EmailAction.SUGGEST_ARCHIVE, EmailAction.SUGGEST_FOLLOWUP,
    }
)

RISKY_ACTIONS = frozenset(
    {
        EmailAction.SEND, EmailAction.ARCHIVE, EmailAction.MOVE, EmailAction.MARK_READ,
        EmailAction.APPLY_SERVER_LABEL, EmailAction.FORWARD_EXTERNAL,
        EmailAction.DOWNLOAD_ATTACHMENT, EmailAction.SHARE_WITH_AGENT,
    }
)

DESTRUCTIVE_ACTIONS = frozenset({EmailAction.DELETE, EmailAction.EXPUNGE})


class EmailActionForbidden(PermissionError):
    """Raised when a destructive action is attempted while disabled."""


class EmailApprovalRequired(PermissionError):
    """Raised when a risky action is attempted without an approval."""


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


def is_safe(action: EmailAction) -> bool:
    return action in SAFE_ACTIONS


def requires_approval(action: EmailAction) -> bool:
    return action in RISKY_ACTIONS or action in DESTRUCTIVE_ACTIONS


def check_action(action: EmailAction, approved: bool = False) -> None:
    """Raise unless the action is permitted under current policy + approval."""
    if action in SAFE_ACTIONS:
        return
    if action in DESTRUCTIVE_ACTIONS:
        allow = _flag("DAYPILOT_EMAIL_ALLOW_DELETE") if action == EmailAction.DELETE else _flag("DAYPILOT_EMAIL_ALLOW_EXPUNGE")
        if not allow:
            raise EmailActionForbidden(
                f"Email action '{action}' is destructive and disabled by policy."
            )
    if action == EmailAction.SEND and not _flag("DAYPILOT_EMAIL_ALLOW_SEND", "true"):
        # Sending can be globally disabled (demo/mock mode).
        raise EmailActionForbidden("Email sending is disabled (DAYPILOT_EMAIL_ALLOW_SEND=false).")
    if not approved:
        raise EmailApprovalRequired(
            f"Email action '{action}' requires explicit user approval before it runs."
        )


def email_enabled() -> bool:
    return _flag("DAYPILOT_EMAIL_ENABLED")
