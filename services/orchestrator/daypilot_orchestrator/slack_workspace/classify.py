"""What kind of message is this, and does it deserve a reply?

Deterministic and model-free, on purpose. Two reasons:

* **Cost and latency.** Every message in every traced conversation passes
  through here. Asking a model "does this need a reply?" thousands of times a
  day is the wrong shape.
* **Restraint.** A model asked to draft a reply will draft one. Ask it about
  "Thanks 👍" and you get *"You're welcome! Let me know if you need anything
  else."* — the exact noise that makes workplace AI something people switch off.
  The classifier's most valuable output is ``NO_DRAFT``.

Classification decides whether the expensive path (context assembly + a model)
runs at all. Getting it wrong in the quiet direction costs a missed suggestion;
getting it wrong in the loud direction costs the user's trust.
"""
from __future__ import annotations

import re

#: Every label the inbox can show.
NEEDS_REPLY = "needs_reply"
ACTION_REQUIRED = "action_required"
DECISION_REQUESTED = "decision_requested"
FYI = "fyi"
ACKNOWLEDGEMENT = "acknowledgement"
SOCIAL = "social"
LOW_PRIORITY = "low_priority"

CLASSIFICATIONS = (
    NEEDS_REPLY, ACTION_REQUIRED, DECISION_REQUESTED,
    FYI, ACKNOWLEDGEMENT, SOCIAL, LOW_PRIORITY,
)

#: Labels that earn a prepared draft. The rest are shown and left alone.
DRAFTABLE = frozenset({NEEDS_REPLY, ACTION_REQUIRED, DECISION_REQUESTED})

#: Which bucket the inbox groups a label under.
INBOX_GROUPS = {
    NEEDS_REPLY: "needs_reply",
    ACTION_REQUIRED: "action",
    DECISION_REQUESTED: "action",
    FYI: "fyi",
    ACKNOWLEDGEMENT: "fyi",
    SOCIAL: "fyi",
    LOW_PRIORITY: "fyi",
}

# A short message that is only thanks/approval, optionally with an emoji.
_ACK = re.compile(
    r"^\s*(thanks?|thank you|thx|ty|ok|okay|got it|noted|sounds good|perfect|great|"
    r"nice|cool|done|\+1|lgtm|ack|will do|makes sense)\b[\s!.,👍🙏✅🎉😄🙌🔥💯]*$",
    re.IGNORECASE,
)
_SOCIAL = re.compile(
    r"\b(good morning|good night|happy birthday|congrats|congratulations|welcome aboard|"
    r"have a good (weekend|evening|holiday)|enjoy your)\b",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"\b(option [ab1-9]|which (one|option|approach)|should we|do we (go|proceed)|"
    r"your call|decide|decision|approve|sign off|go/no-?go|a or b)\b",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(can you|could you|please (review|check|update|send|look|confirm|fix|merge)|"
    r"need you to|assign|take a look|action required|blocking|blocked on you|"
    r"waiting on you|by (today|tomorrow|eod|cob|friday|monday))\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(r"\?")
_FYI = re.compile(
    r"\b(fyi|heads up|for your (information|awareness)|just so you know|no action needed|"
    r"posting here|sharing)\b",
    re.IGNORECASE,
)

#: A bot's own status spam is not a conversation.
_BOT_NOISE = re.compile(
    r"\b(build (passed|failed)|pipeline|deployed to|has joined the channel|"
    r"has left the channel|set the channel topic)\b",
    re.IGNORECASE,
)


def classify(text: str, *, mentioned: bool = False, is_dm: bool = False) -> str:
    """Label one message.

    ``mentioned`` and ``is_dm`` raise the stakes: the same sentence in a busy
    channel and in a direct message are different obligations.
    """
    body = (text or "").strip()
    if not body:
        return LOW_PRIORITY

    # Order matters. Acknowledgement is checked first and on the *whole* string:
    # "thanks — can you also review the PR?" is a request, not a thank-you, and
    # only an anchored match tells those apart.
    if _ACK.match(body):
        return ACKNOWLEDGEMENT
    if _SOCIAL.search(body):
        return SOCIAL
    if _BOT_NOISE.search(body) and not mentioned:
        return LOW_PRIORITY
    if _DECISION.search(body):
        return DECISION_REQUESTED
    if _ACTION.search(body):
        return ACTION_REQUIRED
    # An explicit "FYI" outranks a trailing question mark: "FYI we shipped —
    # anything else you need?" is still a notification.
    if _FYI.search(body):
        return FYI
    if _QUESTION.search(body):
        return NEEDS_REPLY
    if is_dm or mentioned:
        # Addressed to you personally, with no other signal — worth surfacing,
        # but not worth putting words in your mouth.
        return NEEDS_REPLY if is_dm else FYI
    return FYI


def should_draft(classification: str) -> bool:
    """Whether this label earns the context-assembly + generation path."""
    return classification in DRAFTABLE


def inbox_group(classification: str) -> str:
    return INBOX_GROUPS.get(classification, "fyi")
