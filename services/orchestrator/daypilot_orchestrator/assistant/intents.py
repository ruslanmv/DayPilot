"""Server-side intent classification for the assistant (Batch 4).

This is the authority for what an assistant turn means — moved out of the
browser so the routing is deterministic, testable, and identical for every
client. Word-ish matching keeps short tokens (like "today") from matching
inside other words.
"""
from __future__ import annotations

INTENTS = (
    "date", "plan", "replan", "integrations", "email", "approvals", "new_project",
    # Write intents — the assistant only *prepares* these (opens an approval).
    "send_email", "schedule", "coding", "unknown",
)


def classify_intent(q: str) -> str:
    padded = f" {q.lower()} "

    def has(*ws: str) -> bool:
        return any(w in padded for w in ws)

    # Write intents first — a "send this reply" must not be captured by the
    # read-only email-status branch below.
    if has(" send ", " reply to ", " send a reply", " send the email", " email them", " respond to "):
        return "send_email"
    if has(" schedule ", " book ", " create an event", " add to my calendar", " set up a meeting", " put on my calendar"):
        return "schedule"
    if has(" fix the ", " open a pr", " pull request", " write code", " implement ", " code change", " run the coding", " push a fix"):
        return "coding"
    if has(" move ", " replan", " reschedul", " push ", " batch ", " protect ", " swap "):
        return "replan"
    if has(" what day", " which day", "today's date", " date today", " what is today",
           " what's today", " current date", " what time"):
        return "date"
    # Email-specific access questions get an email-status answer.
    if has(" email", " e-mail", " mailbox", " inbox"):
        return "email"
    # Broader integration/provider/calendar/connection questions.
    if has(" calendar", " integration", " connected", " provider", " ollabridge",
           " health", " access to ", " access my ", " can you access"):
        return "integrations"
    if has(" new project", " create project", " start a project", " add project", " create a project"):
        return "new_project"
    if has(" plan", " schedule", " agenda", " my day"):
        return "plan"
    if has(" approv", " pending", " review queue"):
        return "approvals"
    return "unknown"
