"""Email provider registry (batch B9).

Selects the mailbox adapter from configuration. Mock is the safe default;
imap_smtp is the portable content plane for Mailu, generic IMAP/SMTP, and
(with OAuth tokens as the password) Gmail / Microsoft 365. Provisioning via the
Mailu REST admin API is a separate plane and out of the content path.
"""
from __future__ import annotations

import os

from ..adapters.base import MailboxAdapter
from ..adapters.imap_smtp_adapter import ImapSmtpAdapter, ImapSmtpConfig
from ..adapters.mock_adapter import MockMailAdapter

# Documented provider identifiers; gmail/microsoft ride the imap_smtp plane
# using provider-specific hosts and OAuth tokens supplied as the password.
KNOWN_PROVIDERS = ("mock", "mailu", "imap_smtp", "gmail", "microsoft")

_PROVIDER_HOSTS = {
    "gmail": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "microsoft": ("outlook.office365.com", 993, "smtp.office365.com", 587),
}


def get_adapter() -> MailboxAdapter:
    provider = os.getenv("DAYPILOT_EMAIL_PROVIDER", "mock").lower()
    if provider in {"mock", ""}:
        return MockMailAdapter()

    username = os.getenv("EMAIL_USERNAME", os.getenv("IMAP_USERNAME", ""))
    password = os.getenv("EMAIL_PASSWORD", os.getenv("IMAP_PASSWORD", ""))
    if provider in _PROVIDER_HOSTS:
        imap_host, imap_port, smtp_host, smtp_port = _PROVIDER_HOSTS[provider]
    else:
        # mailu / generic imap_smtp
        imap_host = os.getenv("IMAP_HOST", "localhost")
        imap_port = int(os.getenv("IMAP_PORT", "993"))
        smtp_host = os.getenv("SMTP_HOST", os.getenv("IMAP_HOST", "localhost"))
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not username or not password:
        # Missing credentials — stay safe and serve the mock backend.
        return MockMailAdapter()

    return ImapSmtpAdapter(
        ImapSmtpConfig(
            imap_host=imap_host, imap_port=imap_port,
            smtp_host=smtp_host, smtp_port=smtp_port,
            username=username, password=password,
        )
    )
