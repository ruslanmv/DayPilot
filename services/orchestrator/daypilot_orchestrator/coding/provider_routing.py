"""Coding executor routing (batch B6/B7).

Resolves which executor runs a coding block. GitPilot is the retro-compatible
default; Claude Code and Codex are optional executors enabled per deployment and
selectable per project. Every executor implements the same
CodingWorkflowAdapter, so switching one changes nothing downstream.
"""
from __future__ import annotations

import os

import httpx

from .claude_code_adapter import claude_code_from_env
from .codex_adapter import codex_from_env
from .gitpilot_adapter import gitpilot_from_env
from .interface import AdapterCapabilities, CodingWorkflowAdapter

DEFAULT_EXECUTOR = "gitpilot"

_FACTORIES = {
    "gitpilot": gitpilot_from_env,
    "claude_code": claude_code_from_env,
    "codex": codex_from_env,
}

# Optional executors are opt-in per deployment.
_ENABLE_FLAGS = {
    "claude_code": "CLAUDE_CODE_ENABLED",
    "codex": "CODEX_ENABLED",
}


def _normalize_name(name: str) -> str:
    key = name.lower().replace("-", "_")
    return {"git": "gitpilot", "claude": "claude_code", "claudecode": "claude_code"}.get(key, key)


def default_executor() -> str:
    return _normalize_name(os.getenv("DAYPILOT_CODING_EXECUTOR", DEFAULT_EXECUTOR))


def is_enabled(executor: str) -> bool:
    executor = _normalize_name(executor)
    if executor == "gitpilot":
        return True
    flag = _ENABLE_FLAGS.get(executor)
    return bool(flag and os.getenv(flag, "false").lower() == "true")


# Per-project executor overrides, e.g. "proj-a=claude_code,proj-b=codex".
def _project_overrides() -> dict[str, str]:
    raw = os.getenv("DAYPILOT_CODING_PROJECT_OVERRIDES", "")
    overrides: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            project, executor = pair.split("=", 1)
            overrides[project.strip()] = _normalize_name(executor.strip())
    return overrides


def choose_executor(executor: str | None, project_id: str | None) -> str:
    """Resolve the effective executor: explicit > project override > default."""
    if executor:
        candidate = _normalize_name(executor)
    elif project_id and project_id in _project_overrides():
        candidate = _project_overrides()[project_id]
    else:
        candidate = default_executor()
    # Fall back to the default bridge if the choice is unknown or disabled.
    if candidate not in _FACTORIES or not is_enabled(candidate):
        return DEFAULT_EXECUTOR
    return candidate


def resolve_adapter(
    executor: str | None = None,
    *,
    project_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> CodingWorkflowAdapter:
    choice = choose_executor(executor, project_id)
    return _FACTORIES[choice](transport=transport)


def available_executors() -> list[dict]:
    """List executors with their capabilities and enabled state, for the UI."""
    out = []
    for name, factory in _FACTORIES.items():
        caps: AdapterCapabilities = factory().capabilities
        out.append(
            {
                "executor": name,
                "enabled": is_enabled(name),
                "default": name == default_executor(),
                "supportsTests": caps.supports_tests,
                "supportsPr": caps.supports_pr,
                "supportsPlanMode": caps.supports_plan_mode,
                "diffGranularity": caps.diff_granularity,
                "sessionContinuity": caps.session_continuity,
            }
        )
    return out
