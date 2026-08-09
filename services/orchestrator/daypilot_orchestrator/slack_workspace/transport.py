"""How inbound Slack events reach DayPilot, and how they are proven authentic.

Two transports, one pipeline behind them:

``socket``
    Slack's Socket Mode. A process-initiated WebSocket, so nothing has to be
    reachable from the internet. This is the right default for a local-first
    product — asking someone to expose a public HTTPS callback from their laptop
    is asking them not to use the feature.
``http``
    The classic Events API request URL. Needed for a hosted deployment, and the
    only mode where request signing matters, because it is the only mode where
    anyone on the internet can POST to the endpoint.

Whichever arrives, :func:`normalize` produces the same dictionary and
:func:`daypilot_orchestrator.slack_workspace.service.ingest` does the same work.
The transport is a delivery detail; the trust boundary is not.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

#: Transport ids.
SOCKET = "socket"
HTTP = "http"

TRANSPORTS = (SOCKET, HTTP)

#: Slack rejects anything older than five minutes and so do we — the timestamp
#: is what makes a captured, still-validly-signed request unusable later.
REPLAY_WINDOW_SECONDS = 60 * 5

SIGNATURE_HEADER = "x-slack-signature"
TIMESTAMP_HEADER = "x-slack-request-timestamp"
SIGNATURE_VERSION = "v0"


class UntrustedEvent(PermissionError):
    """The request did not prove it came from Slack."""


def configured_transport() -> str:
    """Which transport this deployment is set up for.

    Socket Mode wins when an app-level token is present, because if someone has
    configured one that is what they meant. Explicit configuration overrides.
    """
    explicit = str(os.getenv("DAYPILOT_SLACK_TRANSPORT", "")).strip().lower()
    if explicit in TRANSPORTS:
        return explicit
    return SOCKET if os.getenv("SLACK_APP_TOKEN") else HTTP


def signing_secret() -> str:
    return str(os.getenv("SLACK_SIGNING_SECRET", "")).strip()


def verify_signature(
    body: bytes,
    headers: dict[str, str],
    *,
    secret: str | None = None,
    now: float | None = None,
) -> None:
    """Prove an HTTP-delivered event came from Slack, or raise.

    Raising rather than returning ``False`` is deliberate: a caller that forgets
    to check a boolean has a silent authentication bypass, whereas a caller that
    forgets to catch an exception has a loud 500. Only one of those is a
    security incident.
    """
    key = (secret if secret is not None else signing_secret()).strip()
    if not key:
        # No secret configured means the endpoint cannot authenticate anything.
        # Accepting unsigned events "until it is set up" is how an open relay
        # into someone's workspace gets shipped.
        raise UntrustedEvent("SLACK_SIGNING_SECRET is not configured")

    lowered = {k.lower(): v for k, v in headers.items()}
    timestamp = lowered.get(TIMESTAMP_HEADER, "")
    signature = lowered.get(SIGNATURE_HEADER, "")
    if not timestamp or not signature:
        raise UntrustedEvent("missing Slack signature headers")

    try:
        sent_at = float(timestamp)
    except ValueError as exc:
        raise UntrustedEvent("malformed Slack timestamp") from exc
    if abs((now if now is not None else time.time()) - sent_at) > REPLAY_WINDOW_SECONDS:
        raise UntrustedEvent("Slack timestamp outside the replay window")

    basestring = b"%s:%s:%s" % (SIGNATURE_VERSION.encode(), timestamp.encode(), body)
    expected = SIGNATURE_VERSION + "=" + hmac.new(
        key.encode(), basestring, hashlib.sha256
    ).hexdigest()
    # Constant-time: a byte-by-byte comparison leaks the signature one character
    # at a time to anyone willing to measure.
    if not hmac.compare_digest(expected, signature):
        raise UntrustedEvent("Slack signature mismatch")


def is_url_verification(envelope: dict[str, Any]) -> bool:
    return str(envelope.get("type", "")) == "url_verification"


#: Subtypes that are channel bookkeeping rather than someone talking.
_IGNORED_SUBTYPES = frozenset({
    "message_changed", "message_deleted", "channel_join", "channel_leave",
    "channel_topic", "channel_purpose", "channel_name", "bot_message",
    "thread_broadcast_join", "message_replied",
})


def normalize(envelope: dict[str, Any], *, bot_user_id: str = "") -> dict[str, Any] | None:
    """Flatten a Slack event envelope into what :func:`service.ingest` expects.

    Returns ``None`` for anything that is not a human message — edits, joins,
    the bot's own posts. Filtering here rather than in the pipeline keeps the
    "is this worth a draft?" decision about *content*, not about plumbing.
    """
    event = envelope.get("event") if "event" in envelope else envelope
    if not isinstance(event, dict):
        return None
    if str(event.get("type", "")) not in ("message", "app_mention"):
        return None
    if str(event.get("subtype", "")) in _IGNORED_SUBTYPES:
        return None
    if event.get("bot_id"):
        return None

    user = str(event.get("user") or "")
    if bot_user_id and user == bot_user_id:
        # DayPilot's own approved sends come back as events. Tracing them as
        # incoming would have the assistant drafting replies to itself.
        return None

    channel = str(event.get("channel") or "")
    channel_type = str(event.get("channel_type") or "")
    kind = {"im": "im", "mpim": "mpim", "group": "group"}.get(
        channel_type, "im" if channel.startswith("D") else "channel"
    )
    text = str(event.get("text") or "")

    return {
        "channel": channel,
        "channelKind": kind,
        "channelName": str(event.get("channel_name") or ""),
        "ts": str(event.get("ts") or ""),
        "thread_ts": str(event.get("thread_ts") or "") or None,
        "user": user,
        "userName": str(event.get("user_name") or ""),
        "text": text,
        "direction": "incoming",
        "mentioned": str(event.get("type")) == "app_mention"
        or (bool(bot_user_id) and f"<@{bot_user_id}>" in text),
    }


def describe() -> dict[str, Any]:
    """What the Settings panel shows about event delivery.

    Reports what is *configured*, not what would be nice. A UI that claims
    Socket Mode while no app token exists is a UI that will be believed right up
    until the first message fails to arrive.
    """
    transport = configured_transport()
    return {
        "transport": transport,
        "socketModeConfigured": bool(os.getenv("SLACK_APP_TOKEN")),
        "signingSecretConfigured": bool(signing_secret()),
        # Socket Mode needs no inbound reachability, which is the whole reason
        # it is the local-first default.
        "requiresPublicUrl": transport == HTTP,
        "eventsPath": "/v1/slack/events" if transport == HTTP else None,
    }
