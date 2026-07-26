"""HomePilot remote-agent runtime for DayPilot.

Direction (frozen — see docs/homepilot-runtime-contract.md):
    HomePilot owns the agents. DayPilot connects to them and manages their work.

DayPilot never recreates HomePilot personas, memory, avatars, prompts, sessions,
gallery, or dependency installation. It stores *remote references* to personas
already available in a side-by-side HomePilot install, opens a DayPilot-native
workspace per agent, and routes conversation turns to the real persona over
HomePilot's OpenAI-compatible API — always in propose-only mode, so every
external write stays subject to DayPilot's Approval Center.
"""
from __future__ import annotations

from .contracts import (
    ALLOWED_DIRECTIVES,
    CAPABILITIES,
    HomePilotFeature,
    ToolMode,
    feature_enabled,
    runtime_enabled,
)

__all__ = [
    "ALLOWED_DIRECTIVES",
    "CAPABILITIES",
    "HomePilotFeature",
    "ToolMode",
    "feature_enabled",
    "runtime_enabled",
]
