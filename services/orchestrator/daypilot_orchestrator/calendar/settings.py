"""Calendar behaviour and meeting-context policy.

Two of these settings are a policy the server enforces, not a preference the
browser is trusted with:

* ``contextSources`` is the **allow-list** a meeting brief may read from. The
  assembler asks this module what is permitted and gathers only that; the model
  never gets a tool that can reach an integration on its own.
* ``privateEvents`` decides what a calendar entry marked private contributes.
  The default is metadata only — title, time, attendee count — because the
  alternative is quietly posting the body of somebody's private appointment
  into a prompt.

There is deliberately no "let AI change my calendar without approval" setting.
An external calendar write goes through the Approval Center, and a toggle that
could switch that off would make the guarantee a preference.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from daypilot_knowledge.db import CalendarSettings


class InvalidSetting(ValueError):
    """A setting was outside its allowed set."""


#: Which meetings get a prepared brief.
PREPARE_SCOPES = ("external", "important", "every")

#: What a `private`/`confidential` calendar entry may contribute.
PRIVATE_MODES = ("metadata_only", "full", "skip")

#: Every context source a brief can be granted. `id` is stored;
#: `requires` names an integration provider that must be connected for the
#: source to be usable at all.
CONTEXT_SOURCES: tuple[dict[str, Any], ...] = (
    {"id": "event", "label": "Calendar event & agenda", "requires": None},
    {"id": "projects", "label": "DayPilot projects", "requires": None},
    {"id": "tasks", "label": "Tasks", "requires": None},
    {"id": "documents", "label": "Knowledge documents", "requires": None},
    {"id": "slack", "label": "Slack conversations", "requires": "slack"},
    {"id": "email", "label": "Email threads", "requires": "email"},
    {"id": "github", "label": "GitHub activity", "requires": "github"},
)

CONTEXT_SOURCE_IDS = tuple(s["id"] for s in CONTEXT_SOURCES)

#: The event itself is always available — a brief about a meeting that may not
#: read the meeting would be nonsense — so it is not a real choice.
ALWAYS_ON_SOURCES = ("event",)

DEFAULT_CONTEXT_SOURCES = ["event", "projects", "tasks", "documents"]

#: Buffers are minutes; anything longer than an hour is a scheduling mistake,
#: not a preference.
MAX_BUFFER_MINUTES = 60
MAX_PREP_MINUTES = 60


def get_settings(session: Session, workspace_id: str = "default") -> CalendarSettings:
    """The workspace's settings, created with defaults on first read."""
    row = (
        session.query(CalendarSettings)
        .filter(CalendarSettings.workspace_id == workspace_id)
        .one_or_none()
    )
    if row is None:
        row = CalendarSettings(
            workspace_id=workspace_id,
            context_sources=list(DEFAULT_CONTEXT_SOURCES),
        )
        session.add(row)
        session.flush()
    return row


def _clamp(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return fallback


def normalize_sources(raw: Any) -> list[str]:
    """Keep known ids, drop the rest, and always include the event itself.

    An unknown id is dropped rather than stored: this list is consulted as an
    allow-list, and a typo that silently persisted would be a permission whose
    meaning nobody could look up.
    """
    wanted = {str(s) for s in (raw or []) if isinstance(s, (str, bytes))}
    keep = [s for s in CONTEXT_SOURCE_IDS if s in wanted or s in ALWAYS_ON_SOURCES]
    return keep


def update_settings(
    session: Session, workspace_id: str, patch: dict[str, Any]
) -> CalendarSettings:
    """Apply a partial update. Unknown keys are ignored; bad values raise."""
    row = get_settings(session, workspace_id)

    if "prepareEnabled" in patch:
        row.prepare_enabled = bool(patch["prepareEnabled"])
    if "prepareScope" in patch:
        scope = str(patch["prepareScope"])
        if scope not in PREPARE_SCOPES:
            raise InvalidSetting(f"prepareScope must be one of {PREPARE_SCOPES}, got {scope!r}")
        row.prepare_scope = scope
    if "prepMinutes" in patch:
        row.prep_minutes = _clamp(patch["prepMinutes"], 0, MAX_PREP_MINUTES, row.prep_minutes)
    if "autoPrepBlocks" in patch:
        row.auto_prep_blocks = bool(patch["autoPrepBlocks"])

    if "contextSources" in patch:
        row.context_sources = normalize_sources(patch["contextSources"])
    if "privateEvents" in patch:
        mode = str(patch["privateEvents"])
        if mode not in PRIVATE_MODES:
            raise InvalidSetting(f"privateEvents must be one of {PRIVATE_MODES}, got {mode!r}")
        row.private_events = mode

    if "acceptedAreFixed" in patch:
        row.accepted_are_fixed = bool(patch["acceptedAreFixed"])
    if "ignoreDeclined" in patch:
        row.ignore_declined = bool(patch["ignoreDeclined"])
    if "tentativeBlocks" in patch:
        row.tentative_blocks = bool(patch["tentativeBlocks"])
    if "bufferBeforeMinutes" in patch:
        row.buffer_before_minutes = _clamp(
            patch["bufferBeforeMinutes"], 0, MAX_BUFFER_MINUTES, row.buffer_before_minutes
        )
    if "bufferAfterMinutes" in patch:
        row.buffer_after_minutes = _clamp(
            patch["bufferAfterMinutes"], 0, MAX_BUFFER_MINUTES, row.buffer_after_minutes
        )

    session.flush()
    return row


def serialize(row: CalendarSettings) -> dict[str, Any]:
    return {
        "prepareEnabled": bool(row.prepare_enabled),
        "prepareScope": row.prepare_scope,
        "prepMinutes": int(row.prep_minutes),
        "autoPrepBlocks": bool(row.auto_prep_blocks),
        "contextSources": list(row.context_sources or []),
        "privateEvents": row.private_events,
        "acceptedAreFixed": bool(row.accepted_are_fixed),
        "ignoreDeclined": bool(row.ignore_declined),
        "tentativeBlocks": bool(row.tentative_blocks),
        "bufferBeforeMinutes": int(row.buffer_before_minutes),
        "bufferAfterMinutes": int(row.buffer_after_minutes),
    }


def allowed_context_sources(
    session: Session, workspace_id: str, connected_providers: set[str] | None = None
) -> list[str]:
    """The sources a brief may actually read right now.

    The stored list is intent; this is intent ∩ reality. A user who granted
    Slack context and later disconnected Slack must not have a brief silently
    claim a Slack source it could not read.
    """
    connected = connected_providers or set()
    stored = set(get_settings(session, workspace_id).context_sources or [])
    out = []
    for source in CONTEXT_SOURCES:
        if source["id"] not in stored and source["id"] not in ALWAYS_ON_SOURCES:
            continue
        requires = source["requires"]
        if requires and requires not in connected:
            continue
        out.append(source["id"])
    return out
