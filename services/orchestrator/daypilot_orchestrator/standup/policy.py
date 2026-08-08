"""The rules the standup is not allowed to break, in one place.

Every other module in this package defers to these. They are stated as code
rather than as prose in a docstring because each one is a way the feature could
quietly embarrass the user in a public channel.
"""
from __future__ import annotations

import hashlib

# ---------------------------------------------------------------------------
# Draft lifecycle
# ---------------------------------------------------------------------------

COLLECTING = "COLLECTING"
DRAFT = "DRAFT"
NEEDS_REVIEW = "NEEDS_REVIEW"
APPROVED = "APPROVED"
WAITING_FOR_THREAD = "WAITING_FOR_THREAD"
SENDING = "SENDING"
SENT = "SENT"

THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
SEND_FAILED = "SEND_FAILED"
SKIPPED = "SKIPPED"
EXPIRED = "EXPIRED"

#: States in which the *editable* text may still change.
EDITABLE_STATES = {COLLECTING, DRAFT, NEEDS_REVIEW, THREAD_NOT_FOUND, SEND_FAILED}

#: States that mean this day's update has already gone out, or been abandoned.
TERMINAL_STATES = {SENT, SKIPPED, EXPIRED}


class StandupError(RuntimeError):
    """Any refusal that the caller should surface rather than retry blindly."""


class DraftLocked(StandupError):
    """The draft has been sent or skipped; it is history now."""


class ApprovalRequired(StandupError):
    """Delivery was attempted without a matching approved snapshot."""


class ThreadNotFound(StandupError):
    """No standup thread could be resolved before the cutoff."""


# ---------------------------------------------------------------------------
# Content integrity
# ---------------------------------------------------------------------------

def content_hash(yesterday: str, today: str, blockers: str) -> str:
    """A stable fingerprint of the exact three sections.

    Delivery re-derives this from the frozen snapshot and refuses to send if it
    does not match what was approved. The separator is a character that cannot
    appear in the sections, so ``("a\\nb", "", "")`` and ``("a", "b", "")``
    cannot collide into the same hash.
    """
    joined = "\x00".join((yesterday or "", today or "", blockers or ""))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def delivery_key(workflow_id: str, target_date: str) -> str:
    """The idempotency token for one workflow's post on one standup day.

    A retry after a Slack timeout must not produce a second reply. The key is
    derived from *what the post is*, not from the attempt, so every retry of
    the same day's delivery carries the same token.
    """
    return f"standup:{workflow_id}:{target_date}"


# ---------------------------------------------------------------------------
# What may be said
# ---------------------------------------------------------------------------

#: A bullet with no evidence behind it. Shown to the user as such, and never
#: dressed up as an observation DayPilot made.
MANUAL = "manual"
OBSERVED = "observed"
NEEDS_CONFIRMATION = "needs_confirmation"

#: Default cap per section. Three bullets is what a person actually reads in a
#: standup thread; more than that and the update stops being scanned.
MAX_BULLETS = 3


def classify_bullet(evidence_ids: list[str] | None, *, user_written: bool = False) -> str:
    """How a bullet must be labelled in the review surface."""
    if evidence_ids:
        return OBSERVED
    return MANUAL if user_written else NEEDS_CONFIRMATION


def empty_day_text(policy: str) -> str:
    """What to say on a day with no observed work.

    Fabricating activity is the one failure mode that destroys trust in a
    standup bot permanently, so the honest default says plainly that DayPilot
    saw nothing and leaves the user to fill it in.
    """
    if policy == "skip":
        return ""
    return "• No tracked activity recorded for this day."
