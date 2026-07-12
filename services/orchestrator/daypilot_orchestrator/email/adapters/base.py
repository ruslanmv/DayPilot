"""Unified mailbox adapter interface (batch B9).

The universal content plane is IMAP for reads and APPEND-to-Drafts/Sent, SMTP
submission for sends — so DayPilot behaves identically across Mailu, generic
IMAP/SMTP, Gmail, and Microsoft Graph. Provisioning/admin (Mailu REST) is a
separate plane. The non-destructive policy lives in DayPilot, not the backend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class EmailMessage:
    uid: str
    folder: str
    message_id: str
    subject: str
    sender: str
    recipients: list[str] = field(default_factory=list)
    received_at: str | None = None
    flags: list[str] = field(default_factory=list)
    text: str = ""
    html: str = ""
    has_attachments: bool = False


@dataclass
class DraftResult:
    draft_uid: str
    folder: str = "Drafts"


@dataclass
class SendResult:
    smtp_status: str
    sent_uid: str | None = None
    folder: str = "Sent"


class MailboxAdapter(Protocol):
    provider: str

    def list_inbox(self, limit: int = 50, folder: str = "INBOX") -> list[EmailMessage]: ...

    def fetch_message(self, uid: str, folder: str = "INBOX") -> EmailMessage: ...

    def list_folders(self) -> list[str]: ...

    def create_draft(
        self,
        to: list[str],
        subject: str,
        text: str,
        html: str | None = None,
        in_reply_to: str | None = None,
        signature: str | None = None,
    ) -> DraftResult: ...

    def send_message(
        self, to: list[str], subject: str, text: str, html: str | None = None
    ) -> SendResult: ...
