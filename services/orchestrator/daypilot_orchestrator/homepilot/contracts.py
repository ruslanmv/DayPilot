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
    """Feature flags for the HomePilot integration.

    These are **administrator overrides**, not user-facing on/off switches. The
    integration is a first-class onboarding experience, not an experiment: it is
    ON by default (see ``_FEATURE_DEFAULTS``). An unset flag means "use the
    default"; an admin may pin a flag by setting it explicitly. Only an explicit
    falsey ``RUNTIME`` value hard-disables the whole surface (an admin lock) —
    ordinary users then see "unavailable — disabled by your administrator", never
    the variable name.
    """

    RUNTIME = "DAYPILOT_HOMEPILOT_RUNTIME_ENABLED"
    SYNC = "DAYPILOT_HOMEPILOT_SYNC_ENABLED"
    CHAT = "DAYPILOT_HOMEPILOT_CHAT_ENABLED"
    DELEGATION = "DAYPILOT_HOMEPILOT_DELEGATION_ENABLED"
    IMPORTS = "DAYPILOT_HOMEPILOT_IMPORTS_ENABLED"


# Default state of each flag when the admin has not pinned it. The runtime, agent
# sync, and chat (sessions/memory) are the out-of-the-box experience; delegation
# stays off until the backend is production-ready; the offline ``.hpersona``
# importer stays off (agents are added in HomePilot, not imported).
_FEATURE_DEFAULTS: dict[HomePilotFeature, bool] = {
    HomePilotFeature.RUNTIME: True,
    HomePilotFeature.SYNC: True,
    HomePilotFeature.CHAT: True,
    HomePilotFeature.DELEGATION: False,
    HomePilotFeature.IMPORTS: False,
}

INSTALL_WIZARD_FLAG = "DAYPILOT_HOMEPILOT_INSTALL_WIZARD_ENABLED"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _flag(name: str, default: bool) -> bool:
    """Resolve an override flag: unset/blank → default; else its truthiness."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return _truthy(raw)


def admin_disabled() -> bool:
    """True only when an administrator explicitly set the master flag to a falsey
    value. This is the one state that hard-disables the whole integration; every
    other state is a normal (enabled) connection state."""
    raw = os.getenv(HomePilotFeature.RUNTIME.value)
    return raw is not None and raw.strip() != "" and not _truthy(raw)


def install_wizard_enabled() -> bool:
    """Whether the guided install/connect wizard is offered (default on)."""
    return _flag(INSTALL_WIZARD_FLAG, True)


def runtime_enabled() -> bool:
    """Master switch — on by default; off only under an explicit admin lock."""
    return _flag(HomePilotFeature.RUNTIME.value, _FEATURE_DEFAULTS[HomePilotFeature.RUNTIME])


def feature_enabled(feature: HomePilotFeature) -> bool:
    """A feature is enabled when the master runtime is on AND the feature's own
    override resolves on. A single admin lock on ``RUNTIME`` disables everything."""
    if feature is HomePilotFeature.RUNTIME:
        return runtime_enabled()
    return runtime_enabled() and _flag(feature.value, _FEATURE_DEFAULTS[feature])


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
    "admin_disabled",
    "install_wizard_enabled",
    "INSTALL_WIZARD_FLAG",
    "persona_model_id",
    "is_persona_model",
    "project_id_from_model",
]
