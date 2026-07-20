"""Assistant tool registry + risk classes (Batch 4).

Every capability the assistant can invoke is registered here with an explicit
risk class. The orchestrator consults this registry before dispatching, so the
authority model is deterministic and centralized rather than implied by ad-hoc
call sites:

    READ_ONLY              — reads state only (plan, integrations, approvals…).
    CONTROLLED_LOCAL_WRITE — writes only local DayPilot state (a draft plan, a
                             task from an email). Never egresses, never sends.
    APPROVAL_REQUIRED      — would mutate an external system or send; the
                             assistant may only *prepare* it and open an
                             approval. It never performs the action itself.
    BLOCKED                — never available to the assistant (destructive /
                             egress the product forbids by default).

The assistant never sends email or calls a provider/MCP server directly; those
are APPROVAL_REQUIRED or BLOCKED and are only ever *prepared* here.
"""
from __future__ import annotations

from enum import StrEnum


class ToolRisk(StrEnum):
    READ_ONLY = "read_only"
    CONTROLLED_LOCAL_WRITE = "controlled_local_write"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


# capability id -> (risk, human label)
TOOL_REGISTRY: dict[str, tuple[ToolRisk, str]] = {
    "clock.today": (ToolRisk.READ_ONLY, "Read the current date/time"),
    "planner.read": (ToolRisk.READ_ONLY, "Read today's plan"),
    "planner.readiness": (ToolRisk.READ_ONLY, "Check planning readiness"),
    "planner.generate": (ToolRisk.CONTROLLED_LOCAL_WRITE, "Generate a draft day plan"),
    "planner.replan": (ToolRisk.CONTROLLED_LOCAL_WRITE, "Adjust the draft day plan"),
    "integrations.status": (ToolRisk.READ_ONLY, "Read integration + provider status"),
    "email.status": (ToolRisk.READ_ONLY, "Read mailbox connection status"),
    "approvals.summary": (ToolRisk.READ_ONLY, "Read the approval queue summary"),
    "project.create_wizard": (ToolRisk.CONTROLLED_LOCAL_WRITE, "Open the new-project wizard"),
    # Prepared-only — the assistant may draft but never perform these itself.
    "email.send": (ToolRisk.APPROVAL_REQUIRED, "Send an email (approval required)"),
    "calendar.write": (ToolRisk.APPROVAL_REQUIRED, "Create a calendar event (approval required)"),
    "coding.run": (ToolRisk.APPROVAL_REQUIRED, "Run a coding task / open a PR (approval required)"),
    "mailbox.delete": (ToolRisk.BLOCKED, "Delete mail (blocked)"),
    "mailbox.expunge": (ToolRisk.BLOCKED, "Permanently purge mail (blocked)"),
}


def risk_of(capability: str) -> ToolRisk:
    entry = TOOL_REGISTRY.get(capability)
    return entry[0] if entry else ToolRisk.BLOCKED


def is_invokable(capability: str) -> bool:
    """The assistant may only directly invoke READ_ONLY or CONTROLLED_LOCAL_WRITE
    tools. APPROVAL_REQUIRED tools are prepared (draft + approval) elsewhere and
    BLOCKED tools are never available."""
    return risk_of(capability) in (ToolRisk.READ_ONLY, ToolRisk.CONTROLLED_LOCAL_WRITE)
