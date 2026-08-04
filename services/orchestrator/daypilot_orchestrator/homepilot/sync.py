"""Synchronize DayPilot's remote agent references with a HomePilot install.

Reads HomePilot's persona projects (/projects) and its shared model list
(/v1/models), then upserts a ``HomePilotAgentLink`` per persona. Newly discovered
agents start **disabled** — enabling one is a deliberate DayPilot action and
never changes HomePilot. Personas that vanish from HomePilot are marked
``offline`` (never deleted), preserving history (contract rule 9).
"""
from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import HomePilotAgentLink
from daypilot_knowledge.db.models import utcnow

from .normalizer import is_persona_project, normalize_project, published_model_map


class _Discovery(Protocol):
    def list_projects(self) -> list[dict[str, Any]]: ...
    def list_models(self) -> list[str]: ...


def _derive_status(enabled: bool, shared: bool) -> str:
    """Presence label (text + colour in the UI, never colour alone).

    disabled  — not enabled in DayPilot yet
    available — enabled and chat-capable (persona shared on HomePilot's API)
    offline   — enabled but not currently chat-capable (not shared / removed)
    """
    if not enabled:
        return "disabled"
    return "available" if shared else "offline"


def _existing_links(session: Session, workspace_id: str, connection_id: str) -> list[HomePilotAgentLink]:
    return list(
        session.execute(
            select(HomePilotAgentLink).where(
                HomePilotAgentLink.workspace_id == workspace_id,
                HomePilotAgentLink.connection_id == connection_id,
            )
        ).scalars()
    )


def sync_agents(
    session: Session,
    workspace_id: str,
    connection_id: str,
    client: _Discovery,
    *,
    account_ref: str = "",
    new_agents_disabled: bool = True,
) -> dict[str, Any]:
    """One sync pass. Returns {synced, offline, total, agents:[project_id,...]}.

    ``account_ref`` is the HomePilot account this connection is currently bound
    to. Every synced link is stamped with it, and any existing link from a
    DIFFERENT account is marked offline (never surfaced, never deleted) — so a
    key/account change on the connection can never blend two users' agents.

    If discovery FAILS (transport/HTTP/parse), the pass aborts WITHOUT changing
    any agent state — a transient error must never be read as "all personas were
    deleted" and mark every agent offline. ``new_agents_disabled`` controls
    whether newly discovered agents start disabled (the connection preference).
    """
    # One consistent discovery read; None means a call failed → abort untouched.
    discover = getattr(client, "discover", None)
    if callable(discover):
        disc = discover()
        if disc is None:
            return {"code": "discovery_failed", "synced": 0, "offline": 0, "total": 0, "agents": []}
        projects = disc["projects"]
        models: list[Any] = disc["models"]
    else:  # older client without discover(): fall back to the individual calls
        projects = client.list_projects()
        get_models = getattr(client, "list_persona_models", None)
        models = get_models() if callable(get_models) else client.list_models()

    persona_project_ids = [
        str(p.get("id") or "") for p in projects if is_persona_project(p) and p.get("id")
    ]
    published = published_model_map(models, persona_project_ids)

    by_project = {
        link.homepilot_project_id: link
        for link in _existing_links(session, workspace_id, connection_id)
    }

    seen: set[str] = set()
    synced = 0
    now = utcnow()
    for project in projects:
        norm = normalize_project(project, published)
        if norm is None:
            continue
        pid = norm["homepilot_project_id"]
        seen.add(pid)
        link = by_project.get(pid)
        if link is None:
            link = HomePilotAgentLink(
                workspace_id=workspace_id,
                connection_id=connection_id,
                homepilot_project_id=pid,
                # Disabled by default (the safe choice); the connection can opt new
                # agents in via the "New agents start disabled = off" preference.
                enabled=not new_agents_disabled,
            )
            session.add(link)
        # Refresh safe display metadata (never the prompt/memory).
        link.account_ref = account_ref
        link.homepilot_model_id = norm["homepilot_model_id"]
        link.name = norm["name"]
        link.role = norm["role"]
        link.description = norm["description"]
        link.avatar_ref = norm["avatar_ref"]
        link.thumbnail_ref = norm["thumbnail_ref"]
        link.capabilities_json = norm["capabilities"]
        link.memory_mode = norm["memory_mode"]
        link.source_version = norm["source_version"]
        link.last_synced_at = now
        link.last_seen_at = now
        link.snapshot_json = {"shared": norm["shared"], "capabilities": norm["capabilities"]}
        link.status = _derive_status(link.enabled, norm["shared"])
        synced += 1

    # Personas removed from HomePilot — or belonging to a DIFFERENT account than
    # the one now bound — go offline, never deleted (history preserved, rule 9).
    offline = 0
    for pid, link in by_project.items():
        wrong_account = account_ref and link.account_ref and link.account_ref != account_ref
        if (pid not in seen or wrong_account) and link.status != "offline":
            link.status = "offline"
            offline += 1

    session.flush()
    return {"synced": synced, "offline": offline, "total": len(seen), "agents": sorted(seen)}
