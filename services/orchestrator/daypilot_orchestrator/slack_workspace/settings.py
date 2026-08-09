"""How DayPilot behaves with Slack, and what a Slack draft may read.

Same shape as the calendar's settings module, for the same reason: the context
list is a **permission**, so the catalogue is served to the UI rather than
duplicated in it, and a source whose integration is not connected is reported
unavailable instead of silently ignored.

Two things are absent by design:

* **No "automatically send" setting.** Never auto-sending is an invariant of
  :mod:`.service`, not a preference. A column here would imply it could be off.
* **No "disable recipient protection" beyond a plain flag.** It exists so a
  single-tenant internal deployment can opt out, and it is on by default.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from daypilot_knowledge.db import SlackPreferences


class InvalidSetting(ValueError):
    """A setting was outside its allowed set."""


#: Where DayPilot may draw facts for a Slack draft. `requires` names an
#: integration that must be connected for the source to be usable at all.
CONTEXT_SOURCES: tuple[dict[str, Any], ...] = (
    {"id": "conversation", "label": "Current Slack conversation", "requires": None},
    {"id": "projects", "label": "DayPilot projects", "requires": None},
    {"id": "tasks", "label": "Tasks", "requires": None},
    {"id": "calendar", "label": "Calendar & meetings", "requires": None},
    {"id": "documents", "label": "Knowledge documents", "requires": None},
    {"id": "github", "label": "GitHub activity", "requires": "github"},
    {"id": "email", "label": "Related emails", "requires": "email"},
)

CONTEXT_SOURCE_IDS = tuple(s["id"] for s in CONTEXT_SOURCES)

#: The conversation being replied to is not a real choice — a draft that may not
#: read the message it answers would be nonsense.
ALWAYS_ON_SOURCES = ("conversation",)

DEFAULT_CONTEXT_SOURCES = ["conversation", "projects", "tasks", "calendar", "documents"]

#: standard = the bot connection. personal = user-authorized, which is what
#: actually reaches a human's own DMs.
ACCESS_MODES = ("standard", "personal")


def get_preferences(session: Session, workspace_id: str = "default") -> SlackPreferences:
    """The workspace's preferences, created with defaults on first read."""
    row = (
        session.query(SlackPreferences)
        .filter(SlackPreferences.workspace_id == workspace_id)
        .one_or_none()
    )
    if row is None:
        row = SlackPreferences(
            workspace_id=workspace_id,
            context_sources=list(DEFAULT_CONTEXT_SOURCES),
        )
        session.add(row)
        session.flush()
    return row


def normalize_sources(raw: Any) -> list[str]:
    """Keep known ids, drop the rest, and always include the conversation.

    An unknown id is dropped rather than stored: this list is read as an
    allow-list, and a typo that persisted would be a permission nobody could
    look up.
    """
    wanted = {str(s) for s in (raw or []) if isinstance(s, (str, bytes))}
    return [s for s in CONTEXT_SOURCE_IDS if s in wanted or s in ALWAYS_ON_SOURCES]


def update_preferences(
    session: Session, workspace_id: str, patch: dict[str, Any]
) -> SlackPreferences:
    """Apply a partial update. Unknown keys are ignored; bad values raise."""
    row = get_preferences(session, workspace_id)

    for key, attr in (
        ("draftDirectMessages", "draft_direct_messages"),
        ("draftMentions", "draft_mentions"),
        ("draftParticipatingThreads", "draft_participating_threads"),
        ("draftAllChannelMessages", "draft_all_channel_messages"),
        ("autoPrepare", "auto_prepare"),
        ("usePreviousConversations", "use_previous_conversations"),
        ("recipientProtection", "recipient_protection"),
    ):
        if key in patch:
            setattr(row, attr, bool(patch[key]))

    if "contextSources" in patch:
        row.context_sources = normalize_sources(patch["contextSources"])
    if "accessMode" in patch:
        mode = str(patch["accessMode"])
        if mode not in ACCESS_MODES:
            raise InvalidSetting(f"accessMode must be one of {ACCESS_MODES}, got {mode!r}")
        row.access_mode = mode

    session.flush()
    return row


def serialize(row: SlackPreferences) -> dict[str, Any]:
    return {
        "draftDirectMessages": bool(row.draft_direct_messages),
        "draftMentions": bool(row.draft_mentions),
        "draftParticipatingThreads": bool(row.draft_participating_threads),
        "draftAllChannelMessages": bool(row.draft_all_channel_messages),
        "autoPrepare": bool(row.auto_prepare),
        "contextSources": list(row.context_sources or []),
        "usePreviousConversations": bool(row.use_previous_conversations),
        "recipientProtection": bool(row.recipient_protection),
        "accessMode": row.access_mode,
        # Not a setting — a statement. The UI renders it locked.
        "neverAutomaticallySend": True,
    }


def allowed_context_sources(
    session: Session, workspace_id: str, connected_providers: set[str] | None = None
) -> list[str]:
    """The sources a draft may actually read right now.

    Stored intent ∩ what is connected. Granting GitHub context means nothing
    without GitHub connected, and a draft must not claim a source it could not
    have read.
    """
    connected = connected_providers or set()
    stored = set(get_preferences(session, workspace_id).context_sources or [])
    out = []
    for source in CONTEXT_SOURCES:
        if source["id"] not in stored and source["id"] not in ALWAYS_ON_SOURCES:
            continue
        requires = source["requires"]
        if requires and requires not in connected:
            continue
        out.append(source["id"])
    return out


def drafting_allowed(row: SlackPreferences, *, kind: str, mentioned: bool) -> bool:
    """Whether this conversation is one the user asked to be drafted for."""
    if kind in ("im", "mpim"):
        return bool(row.draft_direct_messages)
    if mentioned:
        return bool(row.draft_mentions)
    return bool(row.draft_all_channel_messages)
