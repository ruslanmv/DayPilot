"""Mock mailbox adapter (batch B9) — demo/dev backend with no real mail server."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .base import DraftResult, EmailMessage, SendResult

_SEED = [
    EmailMessage(
        uid="10492", folder="INBOX", message_id="<alpha@ex>",
        subject="Client Alpha proposal — deadline change", sender="pm@clientalpha.com",
        recipients=["you@company.com"], received_at="2026-07-10T08:15:00Z", flags=[],
        text="We'd like to move delivery from Friday to Monday, and add a weekly reporting requirement.",
        has_attachments=True,
    ),
    EmailMessage(
        uid="10493", folder="INBOX", message_id="<gp@ex>",
        subject="GitPilot build failure on api branch", sender="ci@github.com",
        recipients=["you@company.com"], received_at="2026-07-10T07:40:00Z", flags=["\\Seen"],
        text="The pipeline failed on feature/api-gateway-tests: 2 tests failing.",
    ),
    EmailMessage(
        uid="10494", folder="INBOX", message_id="<md@ex>",
        subject="Matrix Designer: 3 UI recommendations", sender="design@matrix.dev",
        recipients=["you@company.com"], received_at="2026-07-09T18:05:00Z", flags=[],
        text="Contrast on nav labels, card spacing, and a focus ring suggestion.",
    ),
]


@dataclass
class MockMailAdapter:
    provider: str = "mock"
    _messages: list[EmailMessage] = field(default_factory=lambda: list(_SEED))

    def list_inbox(self, limit: int = 50, folder: str = "INBOX") -> list[EmailMessage]:
        return [m for m in self._messages if m.folder == folder][:limit]

    def fetch_message(self, uid: str, folder: str = "INBOX") -> EmailMessage:
        for m in self._messages:
            if m.uid == uid:
                return m
        raise KeyError(uid)

    def list_folders(self) -> list[str]:
        return ["INBOX", "Drafts", "Sent", "Archive", "Important"]

    def create_draft(self, to, subject, text, html=None, in_reply_to=None, signature=None) -> DraftResult:
        body = text + (f"\n\n{signature}" if signature else "")
        draft = EmailMessage(
            uid="d-" + uuid.uuid4().hex[:6], folder="Drafts", message_id=f"<{uuid.uuid4()}@daypilot>",
            subject=subject, sender="you@company.com", recipients=list(to), flags=["\\Draft"], text=body,
        )
        self._messages.append(draft)
        return DraftResult(draft_uid=draft.uid)

    def send_message(self, to, subject, text, html=None) -> SendResult:
        # Mock SMTP: succeeds and APPENDs a copy to Sent (never touches originals).
        sent = EmailMessage(
            uid="s-" + uuid.uuid4().hex[:6], folder="Sent", message_id=f"<{uuid.uuid4()}@daypilot>",
            subject=subject, sender="you@company.com", recipients=list(to), flags=["\\Seen"], text=text,
        )
        self._messages.append(sent)
        return SendResult(smtp_status="250 OK (mock)", sent_uid=sent.uid)
