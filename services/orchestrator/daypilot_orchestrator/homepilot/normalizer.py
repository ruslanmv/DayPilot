"""Normalize HomePilot persona projects into DayPilot agent display metadata.

Extracts ONLY safe display fields (name, role, description, avatar reference,
capabilities). It never copies the persona's system prompt or memory (rule 5) —
those stay in HomePilot and are used live via the chat bridge.
"""
from __future__ import annotations

from typing import Any

from .contracts import is_persona_model, persona_model_id


def is_persona_project(project: dict[str, Any]) -> bool:
    return isinstance(project, dict) and project.get("project_type") == "persona"


def _capabilities(persona_agent: dict[str, Any]) -> list[str]:
    tools = persona_agent.get("allowed_tools") or []
    return [str(t) for t in tools if t][:12]


def normalize_project(
    project: dict[str, Any], shared_model_ids: set[str]
) -> dict[str, Any] | None:
    """Return normalized agent fields for a persona project, or None if it isn't
    a persona. ``shared`` reflects whether the persona is exposed on HomePilot's
    OpenAI-compatible API (``persona:<id>`` present in /v1/models) — only shared
    personas can be chatted with from DayPilot.
    """
    if not is_persona_project(project):
        return None

    project_id = str(project.get("id") or "").strip()
    if not project_id:
        return None

    persona_agent = project.get("persona_agent") or {}
    appearance = project.get("persona_appearance") or {}
    model_id = persona_model_id(project_id)
    shared = model_id in shared_model_ids

    name = (persona_agent.get("label") or project.get("name") or "Persona").strip()
    role = (persona_agent.get("role") or persona_agent.get("category") or "Agent").strip()
    description = (
        project.get("description")
        or persona_agent.get("role")
        or persona_agent.get("category")
        or ""
    ).strip()

    # Avatar/thumbnail are HomePilot-relative references; the DayPilot avatar
    # proxy resolves them server-side (the browser never calls HomePilot).
    thumb = appearance.get("selected_thumb_filename") or appearance.get("selected_filename") or None

    return {
        "homepilot_project_id": project_id,
        "homepilot_model_id": model_id,
        "name": name,
        "role": role,
        "description": description,
        "avatar_ref": appearance.get("selected_filename") or None,
        "thumbnail_ref": thumb,
        "capabilities": _capabilities(persona_agent),
        "memory_mode": persona_agent.get("memory_mode") or None,
        "source_version": str(project.get("updated_at") or project.get("created_at") or "") or None,
        "shared": shared,
    }


def shared_model_ids(model_ids: list[str]) -> set[str]:
    """The subset of model ids that address a persona (``persona:<id>``)."""
    return {m for m in model_ids if is_persona_model(m)}
