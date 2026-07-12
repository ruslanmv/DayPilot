"""Email Sentinel — inbox triage and reply drafting (batch B9).

Classifies urgency and intent, extracts action items, detects schedule impact
(a message that would change the day plan), and drafts replies in the user's
voice. Deterministic heuristics today; Ollabridge (batch B5) phrases the drafts
in a later integration. The Sentinel never sends — it only prepares.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adapters.base import EmailMessage

_URGENT = re.compile(r"\b(urgent|asap|today|eod|deadline|immediately|critical|blocker)\b", re.I)
_MEETING = re.compile(r"\b(meeting|call|sync|invite|reschedul|calendar|agenda)\b", re.I)
_SCHEDULE = re.compile(r"\b(move|reschedul|deadline|delivery|postpone|delay|due date|friday|monday)\b", re.I)
_ACTION = re.compile(r"\b(please|can you|could you|need|request|require|send|review|approve|confirm)\b", re.I)


@dataclass
class SentinelResult:
    urgency: str  # low | medium | high | critical
    intent: str
    action_items: list[str] = field(default_factory=list)
    schedule_impact: bool = False
    reasons: list[str] = field(default_factory=list)


def classify(message: EmailMessage) -> SentinelResult:
    text = f"{message.subject}\n{message.text}"
    reasons: list[str] = []

    urgency = "low"
    if _URGENT.search(text):
        urgency = "high"
        reasons.append("urgency keywords")
    if re.search(r"\b(critical|blocker|immediately)\b", text, re.I):
        urgency = "critical"

    schedule_impact = bool(_SCHEDULE.search(text))
    if schedule_impact:
        reasons.append("schedule-impacting language")

    if _MEETING.search(text) or schedule_impact:
        intent = "scheduling"
    elif re.search(r"\b(fail|error|bug|broken|incident)\b", text, re.I):
        intent = "incident"
    elif _ACTION.search(text):
        intent = "request"
    else:
        intent = "informational"

    action_items = _extract_actions(message.text)
    return SentinelResult(
        urgency=urgency,
        intent=intent,
        action_items=action_items,
        schedule_impact=schedule_impact,
        reasons=reasons,
    )


def _extract_actions(body: str) -> list[str]:
    items: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        if _ACTION.search(sentence) and len(sentence) < 200:
            items.append(sentence.strip())
    return items[:5]


def draft_reply(message: EmailMessage, tone: str = "professional") -> str:
    """Deterministic reply scaffold; Ollabridge refines phrasing later."""
    sender_name = message.sender.split("@")[0].split("<")[0].strip() or "there"
    result = classify(message)
    opener = {
        "professional": f"Hi {sender_name},\n\nThank you for your message.",
        "executive": f"{sender_name},\n\nNoted.",
        "friendly": f"Hi {sender_name},\n\nThanks for reaching out!",
    }.get(tone, f"Hi {sender_name},\n\nThank you for your message.")

    if result.intent == "scheduling":
        middle = "I can accommodate the change. Before we confirm, could you clarify the scope impact so I can adjust the plan?"
    elif result.intent == "request":
        middle = "I'll take a look and follow up shortly with next steps."
    elif result.intent == "incident":
        middle = "I'm looking into this now and will report back with a root cause and fix."
    else:
        middle = "Appreciate the update — I'll factor it into today's plan."

    return f"{opener}\n\n{middle}\n\nBest regards,"
