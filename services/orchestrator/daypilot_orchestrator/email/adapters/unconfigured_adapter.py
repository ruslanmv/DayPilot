"""Unconfigured mailbox adapter (Batch 3).

Used when no real mailbox is connected. It never fabricates messages — every
read returns empty and every write refuses — so the UI shows a truthful
connect-your-email state instead of demo data leaking into production. The mock
adapter is reserved for tests and clearly labelled demo mode.
"""
from __future__ import annotations

from .base import DraftResult, EmailMessage, SendResult


class MailboxNotConfigured(RuntimeError):
    """Raised when an action needs a connected mailbox and there isn't one."""


class UnconfiguredMailAdapter:
    provider = "unconfigured"

    def list_inbox(self, limit: int = 50, folder: str = "INBOX") -> list[EmailMessage]:
        return []

    def fetch_message(self, uid: str, folder: str = "INBOX") -> EmailMessage:
        raise MailboxNotConfigured("No mailbox is connected.")

    def list_folders(self) -> list[str]:
        return []

    def create_draft(self, to, subject, text, html=None, in_reply_to=None, signature=None) -> DraftResult:
        raise MailboxNotConfigured("Connect a mailbox before drafting a reply.")

    def send_message(self, to, subject, text, html=None) -> SendResult:
        raise MailboxNotConfigured("Connect a mailbox before sending.")
