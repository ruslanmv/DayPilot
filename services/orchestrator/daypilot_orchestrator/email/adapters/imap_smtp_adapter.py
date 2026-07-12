"""Universal IMAP/SMTP mailbox adapter (batch B9).

The portable content plane that works against Mailu, generic IMAP/SMTP servers,
and (with OAuth tokens as the password) Gmail and Microsoft 365. Reads use
BODY.PEEK so messages are never implicitly marked read; drafts and sent copies
are written with APPEND — the adapter never deletes or expunges.

Standard-library imaplib/smtplib keep the dependency surface minimal; the class
is constructed with an injectable client factory so it is unit-testable without
a live server.
"""
from __future__ import annotations

import email as email_lib
import imaplib
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import make_msgid, parsedate_to_datetime
from typing import Callable

from .base import DraftResult, EmailMessage, SendResult


@dataclass
class ImapSmtpConfig:
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    use_tls: bool = True


def _default_imap(cfg: ImapSmtpConfig) -> imaplib.IMAP4:
    client = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port) if cfg.use_tls else imaplib.IMAP4(cfg.imap_host, cfg.imap_port)
    client.login(cfg.username, cfg.password)
    return client


def _default_smtp(cfg: ImapSmtpConfig) -> smtplib.SMTP:
    client = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port)
    if cfg.use_tls:
        client.starttls()
    client.login(cfg.username, cfg.password)
    return client


class ImapSmtpAdapter:
    provider = "imap_smtp"

    def __init__(
        self,
        config: ImapSmtpConfig,
        imap_factory: Callable[[ImapSmtpConfig], imaplib.IMAP4] | None = None,
        smtp_factory: Callable[[ImapSmtpConfig], smtplib.SMTP] | None = None,
    ) -> None:
        self.cfg = config
        self._imap_factory = imap_factory or _default_imap
        self._smtp_factory = smtp_factory or _default_smtp

    def list_inbox(self, limit: int = 50, folder: str = "INBOX") -> list[EmailMessage]:
        client = self._imap_factory(self.cfg)
        try:
            client.select(folder, readonly=True)  # readonly => never marks seen
            typ, data = client.uid("search", None, "ALL")
            uids = data[0].split()[-limit:] if data and data[0] else []
            out: list[EmailMessage] = []
            for uid in reversed(uids):
                out.append(self._fetch(client, uid.decode(), folder, peek=True))
            return out
        finally:
            client.logout()

    def fetch_message(self, uid: str, folder: str = "INBOX") -> EmailMessage:
        client = self._imap_factory(self.cfg)
        try:
            client.select(folder, readonly=True)
            return self._fetch(client, uid, folder, peek=True)
        finally:
            client.logout()

    def list_folders(self) -> list[str]:
        client = self._imap_factory(self.cfg)
        try:
            typ, data = client.list()
            folders = []
            for raw in data or []:
                if isinstance(raw, bytes):
                    folders.append(raw.decode().split(' "')[-1].strip('"'))
            return folders or ["INBOX", "Drafts", "Sent"]
        finally:
            client.logout()

    def _fetch(self, client: imaplib.IMAP4, uid: str, folder: str, peek: bool) -> EmailMessage:
        item = "BODY.PEEK[]" if peek else "RFC822"
        typ, data = client.uid("fetch", uid, f"({item})")
        raw = data[0][1] if data and data[0] else b""
        msg = email_lib.message_from_bytes(raw) if raw else MimeMessage()
        received = None
        if msg.get("Date"):
            try:
                received = parsedate_to_datetime(msg["Date"]).isoformat()
            except (TypeError, ValueError):
                received = None
        return EmailMessage(
            uid=uid,
            folder=folder,
            message_id=msg.get("Message-ID", ""),
            subject=msg.get("Subject", ""),
            sender=msg.get("From", ""),
            recipients=[a.strip() for a in (msg.get("To", "") or "").split(",") if a.strip()],
            received_at=received,
            text=_body_text(msg),
            has_attachments=any(part.get_filename() for part in msg.walk()),
        )

    def create_draft(self, to, subject, text, html=None, in_reply_to=None, signature=None) -> DraftResult:
        mime = self._build(to, subject, text, html, in_reply_to, signature)
        client = self._imap_factory(self.cfg)
        try:
            client.append("Drafts", "(\\Draft)", None, mime.as_bytes())
        finally:
            client.logout()
        return DraftResult(draft_uid=mime["Message-ID"])

    def send_message(self, to, subject, text, html=None) -> SendResult:
        mime = self._build(to, subject, text, html, None, None)
        smtp = self._smtp_factory(self.cfg)
        try:
            smtp.send_message(mime)
        finally:
            smtp.quit()
        # APPEND a copy to Sent only after a successful send.
        imap = self._imap_factory(self.cfg)
        try:
            imap.append("Sent", "(\\Seen)", None, mime.as_bytes())
        finally:
            imap.logout()
        return SendResult(smtp_status="250 OK", sent_uid=mime["Message-ID"])

    def _build(self, to, subject, text, html, in_reply_to, signature) -> MimeMessage:
        mime = MimeMessage()
        mime["From"] = self.cfg.username
        mime["To"] = ", ".join(to)
        mime["Subject"] = subject
        mime["Message-ID"] = make_msgid(domain="daypilot")
        if in_reply_to:
            mime["In-Reply-To"] = in_reply_to
            mime["References"] = in_reply_to
        body = text + (f"\n\n{signature}" if signature else "")
        mime.set_content(body)
        if html:
            mime.add_alternative(html, subtype="html")
        return mime


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""
