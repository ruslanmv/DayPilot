"""Normalize HomePilot persona projects into DayPilot agent display metadata.

Extracts ONLY safe display fields (name, role, description, avatar reference,
capabilities). It never copies the persona's system prompt or memory (rule 5) —
those stay in HomePilot and are used live via the chat bridge.
"""
from __future__ import annotations

from typing import Any

from .contracts import is_persona_model, persona_model_id, project_id_from_model


def is_persona_project(project: dict[str, Any]) -> bool:
    return isinstance(project, dict) and project.get("project_type") == "persona"


def _capabilities(persona_agent: dict[str, Any]) -> list[str]:
    tools = persona_agent.get("allowed_tools") or []
    return [str(t) for t in tools if t][:12]


def model_matches_project(model_id: str, project_id: str) -> bool:
    """Whether a published ``/v1/models`` id addresses ``project_id``.

    HomePilot publishes personas as ``persona:<alias>--<short>`` where
    ``short = project_id[:8]`` (current), or ``persona:<project_id>`` (legacy).
    Both — plus the bare ``persona:<short>`` fallback — must map to the project."""
    body = project_id_from_model(model_id)
    if not body or not project_id:
        return False
    if body == project_id:                       # persona:<full-project-id>  (legacy)
        return True
    short = project_id[:8].lower()
    tail = body.rsplit("--", 1)[-1].lower()       # persona:<alias>--<short>
    return tail == short or body.lower() == short  # …or persona:<short>


def published_model_map(models: list[Any], project_ids: list[str]) -> dict[str, str]:
    """Map each project id → its published persona model id (or omit it if the
    persona isn't shared). ``models`` may be ``/v1/models`` id strings or objects
    ``{id, homepilot_project_id}`` — the project-id hint (published by current
    HomePilot) wins; otherwise the id is matched by its ``--<short>`` suffix."""
    persona: list[tuple[str, str | None]] = []
    for m in models:
        if isinstance(m, str):
            mid, hint = m, None
        elif isinstance(m, dict):
            mid, hint = str(m.get("id") or ""), (m.get("homepilot_project_id") or None)
        else:
            continue
        if is_persona_model(mid):
            persona.append((mid, str(hint) if hint else None))

    out: dict[str, str] = {}
    for pid in project_ids:
        match = next((mid for mid, hint in persona if hint and hint == pid), None)
        if match is None:
            match = next((mid for mid, _ in persona if model_matches_project(mid, pid)), None)
        if match is not None:
            out[pid] = match
    return out


def normalize_project(
    project: dict[str, Any], published: dict[str, str] | set[str],
) -> dict[str, Any] | None:
    """Return normalized agent fields for a persona project, or None if it isn't
    a persona. ``published`` maps project id → its published persona model id
    (from :func:`published_model_map`); ``shared`` is whether this project has one.
    A ``set`` of model ids is still accepted for backward compatibility.
    """
    if not is_persona_project(project):
        return None

    project_id = str(project.get("id") or "").strip()
    if not project_id:
        return None

    persona_agent = project.get("persona_agent") or {}
    appearance = project.get("persona_appearance") or {}
    if isinstance(published, dict):
        published_id = published.get(project_id)
    else:  # legacy: a set of shared model-id strings (exact persona:<id> match)
        published_id = persona_model_id(project_id) if persona_model_id(project_id) in published else None
    shared = published_id is not None
    # Store the PUBLISHED id so chat routes to the exact model HomePilot exposes;
    # fall back to the raw form (which HomePilot still resolves) when not shared.
    model_id = published_id or persona_model_id(project_id)

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
