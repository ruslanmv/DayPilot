"""Assistant tool-validation + injection guard (Batch 5).

Two controls sit between an assistant turn and any action:

  1. Tool validation — every capability the orchestrator dispatches is checked
     against the risk registry. READ_ONLY / CONTROLLED_LOCAL_WRITE tools may be
     invoked directly; APPROVAL_REQUIRED tools may only be *prepared* (an
     approval is opened, the action is never performed by the assistant);
     BLOCKED tools are never available.

  2. Injection scanning — the message (and any external content a handler pulls
     in) is scanned for instruction-override / permission-grant / exfiltration
     patterns. A flagged turn can never silently escalate: write actions still
     go through the prepare-approval path, and attempts to bypass approval are
     ignored, not obeyed.
"""
from __future__ import annotations

from ..security.injection_guard import InjectionReport, scan
from .tools import ToolRisk, risk_of


class ToolNotPermitted(RuntimeError):
    """Raised if the orchestrator ever tries to directly perform a BLOCKED or
    APPROVAL_REQUIRED capability instead of preparing it."""


def scan_message(message: str) -> InjectionReport:
    return scan(message, source="assistant_message")


# Phrases that try to get the assistant to bypass the approval gate. They are
# never obeyed — recognized only so the reply can be explicit about it.
_BYPASS_HINTS = (
    "without asking", "without approval", "skip approval", "don't ask",
    "do not ask", "no confirmation", "just send it", "just do it",
    "bypass", "auto-send", "automatically send",
)


def wants_to_bypass_approval(message: str) -> bool:
    m = f" {message.lower()} "
    return any(h in m for h in _BYPASS_HINTS)


def requires_approval(capability: str) -> bool:
    return risk_of(capability) == ToolRisk.APPROVAL_REQUIRED


def assert_not_directly_performed(capability: str) -> None:
    """Guard the deterministic-authority invariant: the assistant must never
    directly perform an approval-required or blocked capability."""
    risk = risk_of(capability)
    if risk in (ToolRisk.APPROVAL_REQUIRED, ToolRisk.BLOCKED):
        raise ToolNotPermitted(
            f"{capability} ({risk.value}) cannot be performed by the assistant; it is only prepared."
        )
