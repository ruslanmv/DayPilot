"""Turning assembled facts into a message someone would actually send.

Deterministic by default, for the same reason the standup compiles rather than
generates: a draft built from facts can be traced back to them, and a draft
nobody can trace is a draft nobody should send. A model can replace
:func:`draft_text` later — the provenance contract does not change, because the
facts are assembled and recipient-filtered *before* generation either way.

Destination changes the register. A 1:1 DM and a post to a 38-person channel are
not the same message, and drafting them identically is the tell of a generic
assistant.
"""
from __future__ import annotations

from .classify import ACTION_REQUIRED, DECISION_REQUESTED, NEEDS_REPLY
from .context import SlackContext

#: How a message reads, by where it is going.
STYLE_DM = "dm"
STYLE_GROUP = "group"
STYLE_CHANNEL = "channel"

STYLE_BY_KIND = {"im": STYLE_DM, "mpim": STYLE_GROUP, "channel": STYLE_CHANNEL,
                 "group": STYLE_CHANNEL}

#: The four rewrites the composer offers. Deliberately four and not fifteen —
#: a wall of tone buttons is a worse interface than a text box.
TRANSFORMS = ("shorter", "direct", "detailed", "friendly")


def style_for(kind: str) -> str:
    return STYLE_BY_KIND.get(kind, STYLE_DM)


def _lead(classification: str, counterpart: str) -> str:
    who = counterpart.split()[0] if counterpart else ""
    if classification == DECISION_REQUESTED:
        return f"{who}, here's where I land." if who else "Here's where I land."
    if classification == ACTION_REQUIRED:
        return f"Thanks {who} — picking this up." if who else "Picking this up."
    return f"Hi {who}," if who else "Hi,"


#: How the draft introduces its evidence, by what was asked.
_FRAME = {
    DECISION_REQUESTED: "Here's what's informing the call:",
    ACTION_REQUIRED: "Where it stands right now:",
    NEEDS_REPLY: "Here's where things stand:",
}


def draft_text(
    context: SlackContext,
    *,
    classification: str = NEEDS_REPLY,
    style: str = STYLE_DM,
    counterpart: str = "",
) -> str:
    """Compose a reply from the facts that survived the recipient filter.

    Two disciplines, both visible in the output:

    * **It does not answer questions it cannot answer.** Asked "can we ship
      before Thursday?", DayPilot knows what is in flight and what is blocked —
      it does not know the answer. So the draft presents the evidence and
      promises a confirmation, rather than asserting a date nobody checked. A
      model can replace this function and *will* phrase a real answer; the
      contract that it may only use these facts does not change.
    * **Evidence is listed, not welded into a sentence.** Concatenating
      retrieved strings into prose reads like a machine emptying its pockets.
      Three short lines under a frame reads like a colleague who checked.

    With no facts it says so, rather than inventing a confident answer — the
    same discipline as the standup, where a day with no tracked activity says so
    instead of manufacturing progress.
    """
    # Conversation quotes are context for the reader, not content for the reply.
    facts = [f for f in context.facts() if " said: " not in f]
    blocked = [f for f in facts if "blocked" in f.lower()]

    if style == STYLE_CHANNEL:
        if not facts:
            return ("Quick update: no change to report since the last one. I'll post again "
                    "when something moves.")
        bullets = "\n".join(f"• {f.rstrip('.')}" for f in facts[:5])
        head = ("Before we decide, here's the current state:"
                if classification == DECISION_REQUESTED else "Update:")
        tail = ("Happy to go either way — I'd like the architecture discussion to settle "
                "the open point first." if classification == DECISION_REQUESTED
                else "I'll follow up here as this moves.")
        return f"{head}\n{bullets}\n\n{tail}"

    if not facts:
        return ("Thanks — I don't have anything solid to add yet. Let me check and come "
                "back to you shortly.")

    bullets = "\n".join(f"• {f.rstrip('.')}" for f in facts[:3])
    frame = _FRAME.get(classification, _FRAME[NEEDS_REPLY])
    close = ("I'll confirm as soon as that clears." if blocked
             else "I'll confirm once I've checked the remaining dependency.")

    if style == STYLE_GROUP:
        return f"{_lead(classification, counterpart)} {frame}\n{bullets}\n\n{close}"
    return f"{_lead(classification, counterpart)}\n\n{frame}\n{bullets}\n\n{close}"


def transform(text: str, kind: str) -> str:
    """Apply one of the four quick rewrites.

    Deterministic string surgery, not a model call: these are meant to feel
    instant, and "shorter" should mean shorter rather than *differently worded
    and possibly a different claim*. Anything subtler goes through the assistant
    panel's natural-language refinement instead.
    """
    body = (text or "").strip()
    if not body:
        return body
    if kind == "shorter":
        sentences = [s.strip() for s in body.replace("\n", " ").split(". ") if s.strip()]
        kept = sentences[: max(1, len(sentences) // 2)]
        out = ". ".join(s.rstrip(".") for s in kept)
        return out + ("." if not out.endswith(".") else "")
    if kind == "direct":
        for filler in ("I think ", "I believe ", "Just ", "Maybe ", "perhaps ",
                       "It seems that ", "I would say "):
            body = body.replace(filler, "")
        return body.replace("Let me know if you need more detail.", "").strip()
    if kind == "detailed":
        if "Happy to walk through" in body:
            return body
        return f"{body}\n\nHappy to walk through the detail if that's useful."
    if kind == "friendly":
        if body.lower().startswith(("hi", "hey", "hello", "thanks")):
            return body
        return f"Hi — {body[0].lower()}{body[1:]}"
    return body


def refine(text: str, instruction: str) -> str:
    """A natural-language edit to the draft.

    The deterministic fallback honours the handful of instructions that are
    unambiguous and safe to apply without a model — notably *removing* a
    commitment, which is the instruction where getting it wrong matters most. It
    never invents a claim; when it does not understand, it returns the text
    unchanged and the caller reports that nothing was applied.
    """
    body = (text or "").strip()
    want = (instruction or "").lower()
    if not body or not want:
        return body

    if any(k in want for k in ("shorter", "concise", "brief", "trim")):
        body = transform(body, "shorter")
    if any(k in want for k in ("direct", "blunt", "to the point")):
        body = transform(body, "direct")
    if any(k in want for k in ("friendly", "warmer", "softer")):
        body = transform(body, "friendly")
    if any(k in want for k in ("detail", "expand", "more context")):
        body = transform(body, "detailed")

    # "Don't promise Friday" / "don't commit to a date" — soften a commitment
    # rather than delete the sentence, so the reply still answers the question.
    if any(k in want for k in ("don't promise", "do not promise", "don't commit",
                               "do not commit", "no commitment")):
        for hard, soft in (
            ("we will ", "we're aiming to "),
            ("We will ", "We're aiming to "),
            ("I will ", "I'm aiming to "),
            ("it will be ", "we're targeting "),
        ):
            body = body.replace(hard, soft)
        if "targeting" not in body.lower() and "aiming" not in body.lower():
            body = f"{body}\n\nTreat that as a target rather than a commitment for now."
    return body
