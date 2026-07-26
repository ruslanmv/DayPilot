"""Frozen HomePilot integration contract (Phase 0).

Encodes the non-negotiable rules of the remote-runtime integration as code so the
rest of the system can depend on them. Nothing here talks to the network; it is
pure policy + shape definitions shared by the client, sync, directive validator,
and action mapper.

The ten rules (mirrored in docs/homepilot-runtime-contract.md):
  1.  HomePilot and DayPilot have separate databases.
  2.  DayPilot never reads HomePilot database tables directly.
  3.  DayPilot never shares HomePilot storage volumes.
  4.  The browser never calls HomePilot directly.
  5.  DayPilot stores a remote agent *reference*, not a copied persona.
  6.  HomePilot cannot execute DayPilot email/calendar/project/coding actions.
  7.  HomePilot *proposes* actions; DayPilot validates and executes them.
  8.  Every external write remains subject to DayPilot approval.
  9.  Removing an agent in HomePilot marks it offline in DayPilot — never deletes
      historical tasks or conversations.
  10. The local ``.hpersona`` importer remains only as an optional offline fallback.
"""
from __future__ import annotations

import os
from enum import Enum


class ToolMode(str, Enum):
    """How HomePilot may act on a persona's agentic tools for a bridged request.

    DayPilot ALWAYS uses ``propose`` — HomePilot reasons with the persona's full
    identity/memory but returns proposed operations as structured directives
    instead of executing external writes. ``disabled``/``execute`` exist for the
    contract's completeness and must never be sent by DayPilot in propose-only
    mode.
    """

    DISABLED = "disabled"
    PROPOSE = "propose"
    EXECUTE = "execute"


# The only directive types DayPilot accepts from a (untrusted) model response.
# Anything else is rejected while the plain-text reply is still preserved.
ALLOWED_DIRECTIVES: frozenset[str] = frozenset(
    {
        "task.create",
        "task.update",
        "task.complete",
        "task.block",
        "progress.report",
        "delegate.request",
        "daypilot.action.propose",
        "artifact.attach",
    }
)

# DayPilot capabilities a persona directive may *propose*. Execution of any of
# these still creates a draft + Approval and runs through DayPilot's own
# integrations — HomePilot never performs the action itself.
CAPABILITIES: frozenset[str] = frozenset(
    {
        "email.send",
        "calendar.create",
        "calendar.update",
        "calendar.cancel",
        "coding.run",
        "github.change",
        "message.send",
        "document.generate",
        "finance.change",
        "hr.change",
        "system.change",
    }
)

# Directive types that DayPilot may apply automatically (no approval): they only
# create/track internal work. Everything that touches the outside world goes via
# ``daypilot.action.propose`` → draft → Approval.
AUTO_APPLY_DIRECTIVES: frozenset[str] = frozenset(
    {"task.create", "task.update", "task.complete", "task.block", "progress.report", "artifact.attach"}
)

# Delegation safety limits (Phase 10).
MAX_DELEGATION_DEPTH = 2
MAX_WORKER_AGENTS = 3
MAX_CHILD_TASKS = 10

# Validation bounds for untrusted directive payloads (Phase 8).
MAX_DIRECTIVES_PER_TURN = 12
MAX_TITLE_LEN = 200
MAX_TEXT_LEN = 4000
VALID_PRIORITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})

# Task lifecycle (Phase 8) — a draft is NEVER shown as completed.
TASK_STATES: frozenset[str] = frozenset(
    {"planned", "active", "waiting_for_input", "waiting_for_approval", "blocked", "completed", "failed", "cancelled"}
)

# Agent presence, surfaced in the directory (text + colour, never colour alone).
AGENT_STATUSES: frozenset[str] = frozenset(
    {"available", "working", "busy", "needs_approval", "offline", "disabled"}
)


class HomePilotFeature(str, Enum):
    """Feature flags gating each phase. Everything is OFF until explicitly set."""

    RUNTIME = "DAYPILOT_HOMEPILOT_RUNTIME_ENABLED"
    SYNC = "DAYPILOT_HOMEPILOT_SYNC_ENABLED"
    CHAT = "DAYPILOT_HOMEPILOT_CHAT_ENABLED"
    DELEGATION = "DAYPILOT_HOMEPILOT_DELEGATION_ENABLED"
    IMPORTS = "DAYPILOT_HOMEPILOT_IMPORTS_ENABLED"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def runtime_enabled() -> bool:
    """Master switch — all other HomePilot features imply this being on."""
    return _truthy(os.getenv(HomePilotFeature.RUNTIME.value))


def feature_enabled(feature: HomePilotFeature) -> bool:
    """A feature is enabled only when BOTH the master runtime flag and the
    feature's own flag are set — so a single master switch disables everything."""
    if feature is HomePilotFeature.RUNTIME:
        return runtime_enabled()
    return runtime_enabled() and _truthy(os.getenv(feature.value))


# HomePilot addresses a persona as this model id on its OpenAI-compatible API.
def persona_model_id(project_id: str) -> str:
    return f"persona:{project_id}"


def is_persona_model(model_id: str) -> bool:
    return isinstance(model_id, str) and model_id.startswith("persona:")


def project_id_from_model(model_id: str) -> str:
    return model_id.split(":", 1)[1] if is_persona_model(model_id) else ""


__all__ = [
    "ToolMode",
    "ALLOWED_DIRECTIVES",
    "AUTO_APPLY_DIRECTIVES",
    "CAPABILITIES",
    "TASK_STATES",
    "AGENT_STATUSES",
    "HomePilotFeature",
    "MAX_DELEGATION_DEPTH",
    "MAX_WORKER_AGENTS",
    "MAX_CHILD_TASKS",
    "MAX_DIRECTIVES_PER_TURN",
    "MAX_TITLE_LEN",
    "MAX_TEXT_LEN",
    "VALID_PRIORITIES",
    "runtime_enabled",
    "feature_enabled",
    "persona_model_id",
    "is_persona_model",
    "project_id_from_model",
]
