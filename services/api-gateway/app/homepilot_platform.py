"""Backend-owned HomePilot connection + remote-agent management (gateway).

The browser never talks to HomePilot (contract rule 4) — this module is the only
path. It reuses the Integration credential store for the base URL + API key
(secret-by-reference) and persists only safe metadata on ``IntegrationConnection``
(provider ``homepilot``). Remote agents are stored as ``HomePilotAgentLink`` rows
(references, not copies).
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, HomePilotAgentLink, IntegrationConnection, Task
from daypilot_knowledge.db.models import utcnow
from daypilot_orchestrator.homepilot import action_mapping as hp_actions
from daypilot_orchestrator.homepilot import session as hp_session
from daypilot_orchestrator.homepilot import task_mapper as hp_mapper
from daypilot_orchestrator.homepilot.client import HomePilotClient
from daypilot_orchestrator.homepilot.directives import validate_directives
from daypilot_orchestrator.homepilot.contracts import (
    HomePilotFeature,
    ToolMode,
    feature_enabled,
    persona_model_id,
    runtime_enabled,
)
from daypilot_orchestrator.homepilot.sync import sync_agents
from daypilot_orchestrator.integrations.credentials import credential_store

PROVIDER = "homepilot"
_CAPABILITIES = [
    "homepilot.health",
    "homepilot.personas.list",
    "homepilot.persona.chat",
    "homepilot.persona.sessions",
    "homepilot.assets.read",
]


def _default_base_url() -> str:
    return os.getenv("HOMEPILOT_BASE_URL", "http://homepilot:7860/api").strip()


# ---- connection helpers -----------------------------------------------------

def _secret(connection_id: str) -> dict[str, str]:
    try:
        return credential_store().get(f"homepilot:{connection_id}") or {}
    except Exception:  # noqa: BLE001 - missing/again-later secret is not fatal
        return {}


def _client_for(row: IntegrationConnection) -> HomePilotClient | None:
    secret = _secret(row.id)
    base = secret.get("base_url") or _default_base_url()
    if not base:
        return None
    return HomePilotClient(base_url=base, api_key=secret.get("api_key") or None)


def _remote_kind(base_url: str) -> str:
    """Classify a connection target as cloud vs local. A cloud HomePilot
    (homepilot.ruslanmv.com, a Hugging Face Space, or any non-loopback public
    host) is bound to a real per-user account; a local install is same-machine."""
    host = (base_url or "").split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    if host in ("localhost", "127.0.0.1", "::1", "homepilot", "host.docker.internal"):
        return "local"
    if "ruslanmv.com" in host or host.endswith(".hf.space") or "hf.space" in host:
        return "cloud"
    return "cloud" if "." in host else "local"


def _fingerprint(api_key: str | None) -> str:
    """A stable, non-reversible account fingerprint for an older HomePilot with
    no identity endpoint — still binds agents to *an* account so a key change
    can't silently blend two accounts. Never the key itself."""
    import hashlib

    if not api_key:
        return "shared"
    return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]


def _resolve_account(row: IntegrationConnection) -> dict[str, str]:
    """Which HomePilot account this connection is bound to. Prefers HomePilot's
    identity endpoint; falls back to a credential fingerprint. Never stores or
    returns a secret."""
    secret = _secret(row.id)
    base = secret.get("base_url") or _default_base_url()
    client = _client_for(row)
    ident = None
    getter = getattr(client, "identity", None)
    if callable(getter):
        try:
            ident = getter()
        except Exception:  # noqa: BLE001 - identity is best-effort; fall back to a fingerprint
            ident = None
    if ident and ident.get("account_ref"):
        return {
            "account_ref": str(ident.get("account_ref")),
            "account_label": str(ident.get("account_label") or ident.get("account_ref")),
            "remote_kind": _remote_kind(base),
        }
    ref = _fingerprint(secret.get("api_key"))
    label = "Shared instance" if ref == "shared" else "This HomePilot"
    return {"account_ref": ref, "account_label": label, "remote_kind": _remote_kind(base)}


def _public(row: IntegrationConnection) -> dict[str, Any]:
    """Safe view — base host + bound account, never the key."""
    secret = _secret(row.id)
    base = secret.get("base_url") or _default_base_url()
    return {
        "id": row.id,
        "workspaceId": row.workspace_id,
        "baseUrl": base,
        "status": row.status,
        "capabilities": list(row.capabilities or []),
        # Which HomePilot account this connection is bound to (multi-account
        # security). Label is safe to show; the ref is opaque; the key is never here.
        "accountRef": secret.get("account_ref") or "",
        "accountLabel": secret.get("account_label") or "",
        "remoteKind": secret.get("remote_kind") or _remote_kind(base),
        # A11: whether this HomePilot supports the propose bridge, or is legacy
        # chat-only (plain replies, no directives).
        "chatMode": secret.get("chat_mode") or "unknown",
        "bridgeVersion": secret.get("bridge_version") or "",
        "lastTestedAt": row.last_activity_at.isoformat() if row.last_activity_at else None,
        "lastError": row.detail or None,
    }


def _get_connection(session: Session, workspace_id: str, connection_id: str) -> IntegrationConnection | None:
    return session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.provider == PROVIDER,
        )
    ).scalar_one_or_none()


def _first_connection(session: Session, workspace_id: str) -> IntegrationConnection | None:
    return session.execute(
        select(IntegrationConnection)
        .where(IntegrationConnection.workspace_id == workspace_id, IntegrationConnection.provider == PROVIDER)
        .order_by(IntegrationConnection.created_at.asc())
    ).scalars().first()


# ---- feature gate -----------------------------------------------------------

def enabled() -> bool:
    return runtime_enabled()


def imports_enabled() -> bool:
    return feature_enabled(HomePilotFeature.IMPORTS)


def _gallery_url(base_url: str) -> str:
    """The HomePilot web app / gallery URL derived from the API base (strip the
    trailing ``/api``). Where the user creates and manages their agents."""
    base = (base_url or "").rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")]
    return base or _default_base_url()


def add_info(session: Session, workspace_id: str) -> dict[str, Any]:
    """Everything the 'Add agent' screen needs: whether a HomePilot connection
    exists, its gallery URL, and whether the offline importer is available."""
    row = _first_connection(session, workspace_id)
    base = (_secret(row.id).get("base_url") if row is not None else "") or _default_base_url()
    return {
        "connected": bool(row is not None and row.status == "connected"),
        "connectionId": row.id if row is not None else None,
        "galleryUrl": _gallery_url(base),
        "importsEnabled": imports_enabled(),
    }


def hpersona_preview(data: bytes) -> dict[str, Any]:
    from daypilot_orchestrator.homepilot import hpersona

    return hpersona.inspect(data)


def hpersona_import(session: Session, workspace_id: str, data: bytes) -> dict[str, Any]:
    from daypilot_orchestrator.homepilot import hpersona

    return hpersona.import_local(session, workspace_id, data)


# ---- connections ------------------------------------------------------------

def connect(session: Session, workspace_id: str, base_url: str | None, api_key: str | None) -> dict[str, Any]:
    """Create/update the HomePilot connection and test it. Secrets go to the
    credential store; only safe metadata is persisted."""
    base = (base_url or _default_base_url()).strip()
    row = _first_connection(session, workspace_id)
    if row is None:
        row = IntegrationConnection(workspace_id=workspace_id, provider=PROVIDER, auth_type="api_key")
        session.add(row)
        session.flush()
    row.capabilities = _CAPABILITIES
    credential_store().put(f"homepilot:{row.id}", {"base_url": base, "api_key": (api_key or "").strip()})

    result = _probe(row)
    row.status = result["status"]
    row.detail = result.get("detail", "")
    row.last_activity_at = utcnow()
    if result["code"] == "connected":
        _store_account(row)     # bind the connection to its HomePilot account
        _store_chat_mode(row)   # probe bridge capability (A11): bridge vs legacy chat-only
    session.flush()
    return {"connection": _public(row), "code": result["code"]}


def _store_account(row: IntegrationConnection) -> dict[str, str]:
    """Resolve + persist the bound HomePilot account into the credential store
    (non-secret metadata alongside the key). Returns the account dict."""
    account = _resolve_account(row)
    secret = _secret(row.id)
    secret.update(account)
    credential_store().put(f"homepilot:{row.id}", secret)
    return account


def _store_chat_mode(row: IntegrationConnection) -> str:
    """Capability probe (A11). Bridge-aware HomePilot advertises
    ``/v1/integrations/daypilot/capabilities`` → ``chat_mode='bridge'`` (directives
    supported). Its absence means a legacy HomePilot → ``chat_mode='chat_only'``:
    plain replies still work, but no proposed directives. Stored so the UI can
    say so up front instead of discovering it turn by turn."""
    client = _client_for(row)
    caps = None
    getter = getattr(client, "capabilities", None)
    if callable(getter):
        try:
            caps = getter()
        except Exception:  # noqa: BLE001 - probe is best-effort
            caps = None
    mode = "bridge" if caps else "chat_only"
    secret = _secret(row.id)
    secret["chat_mode"] = mode
    secret["bridge_version"] = str((caps or {}).get("bridge_version") or "")
    credential_store().put(f"homepilot:{row.id}", secret)
    return mode


def _probe(row: IntegrationConnection) -> dict[str, Any]:
    client = _client_for(row)
    if client is None:
        return {"status": "unconfigured", "code": "unconfigured", "detail": "No base URL configured."}
    health = client.health()
    if not health.reachable:
        return {"status": "unreachable", "code": health.error or "unreachable",
                "detail": "HomePilot is not reachable at that address."}
    if health.error == "unauthorized":
        return {"status": "unauthorized", "code": "unauthorized", "detail": "HomePilot rejected the API key."}
    return {"status": "connected", "code": "connected", "detail": ""}


def list_connections(session: Session, workspace_id: str) -> dict[str, Any]:
    rows = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id, IntegrationConnection.provider == PROVIDER
        )
    ).scalars()
    return {"connections": [_public(r) for r in rows]}


def test_connection(session: Session, workspace_id: str, connection_id: str) -> dict[str, Any]:
    row = _get_connection(session, workspace_id, connection_id)
    if row is None:
        return {"code": "not_found"}
    result = _probe(row)
    row.status = result["status"]
    row.detail = result.get("detail", "")
    row.last_activity_at = utcnow()
    if result["code"] == "connected":
        _store_chat_mode(row)  # re-probe bridge capability (A11)
    session.flush()
    return {"code": result["code"], "connection": _public(row)}


def connection_status(session: Session, workspace_id: str, connection_id: str) -> dict[str, Any]:
    row = _get_connection(session, workspace_id, connection_id)
    if row is None:
        return {"code": "not_found"}
    return {"connection": _public(row)}


def delete_connection(session: Session, workspace_id: str, connection_id: str) -> dict[str, Any]:
    row = _get_connection(session, workspace_id, connection_id)
    if row is None:
        return {"deleted": False}
    # Keep agent links (history) but mark them offline — never delete history.
    for link in session.execute(
        select(HomePilotAgentLink).where(
            HomePilotAgentLink.workspace_id == workspace_id, HomePilotAgentLink.connection_id == connection_id
        )
    ).scalars():
        link.status = "offline"
    try:
        credential_store().delete(f"homepilot:{connection_id}")
    except Exception:  # noqa: BLE001
        pass
    session.delete(row)
    session.flush()
    return {"deleted": True}


# ---- sync -------------------------------------------------------------------

def sync(session: Session, workspace_id: str, connection_id: str) -> dict[str, Any]:
    if not feature_enabled(HomePilotFeature.SYNC):
        return {"code": "sync_disabled"}
    row = _get_connection(session, workspace_id, connection_id)
    if row is None:
        return {"code": "not_found"}
    client = _client_for(row)
    if client is None:
        return {"code": "unconfigured"}
    # Re-resolve the bound account each sync so a key/account change re-scopes
    # agents to the current account instead of blending with the previous one.
    account = _store_account(row)
    result = sync_agents(session, workspace_id, connection_id, client, account_ref=account["account_ref"])
    row.last_activity_at = utcnow()
    session.flush()
    return {"code": "synced", **result}


# ---- agent profiles ---------------------------------------------------------

def _public_profile(link: HomePilotAgentLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "connectionId": link.connection_id,
        "homepilotProjectId": link.homepilot_project_id,
        "homepilotModelId": link.homepilot_model_id,
        "name": link.name,
        "role": link.role,
        "description": link.description,
        "avatarUrl": f"/v1/agents/profiles/{link.id}/avatar"
        if (link.thumbnail_ref or link.avatar_ref or (link.snapshot_json or {}).get("avatar_data_uri"))
        else None,
        "capabilities": list(link.capabilities_json or []),
        "memoryMode": link.memory_mode,
        "sourceVersion": link.source_version,
        "enabled": bool(link.enabled),
        "favorite": bool(link.favorite),
        "status": link.status,
        "lastSyncedAt": link.last_synced_at.isoformat() if link.last_synced_at else None,
        "lastSeenAt": link.last_seen_at.isoformat() if link.last_seen_at else None,
    }


def list_profiles(session: Session, workspace_id: str) -> dict[str, Any]:
    rows = session.execute(
        select(HomePilotAgentLink)
        .where(HomePilotAgentLink.workspace_id == workspace_id)
        .order_by(HomePilotAgentLink.favorite.desc(), HomePilotAgentLink.name.asc())
    ).scalars()
    return {"profiles": [_public_profile(r) for r in rows]}


def _get_link(session: Session, workspace_id: str, link_id: str) -> HomePilotAgentLink | None:
    return session.execute(
        select(HomePilotAgentLink).where(
            HomePilotAgentLink.id == link_id, HomePilotAgentLink.workspace_id == workspace_id
        )
    ).scalar_one_or_none()


def get_profile(session: Session, workspace_id: str, link_id: str) -> dict[str, Any] | None:
    link = _get_link(session, workspace_id, link_id)
    return _public_profile(link) if link else None


def patch_profile(session: Session, workspace_id: str, link_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    """Enable/disable or favorite an agent in DayPilot. Never changes HomePilot."""
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return None
    if "enabled" in patch:
        link.enabled = bool(patch["enabled"])
        shared = bool((link.snapshot_json or {}).get("shared"))
        link.status = ("available" if shared else "offline") if link.enabled else "disabled"
    if "favorite" in patch:
        link.favorite = bool(patch["favorite"])
    session.flush()
    return _public_profile(link)


# ---- chat bridge (A6) -------------------------------------------------------

def _parse_persona_response(resp: dict[str, Any]) -> tuple[str, Any, Any]:
    """Pull (content, x_directives, x_homepilot) out of an OpenAI-compatible
    persona response. A legacy (non-bridge) HomePilot simply omits the x_* keys,
    which is how we degrade to chat-only."""
    content = ""
    choices = resp.get("choices") or []
    if choices and isinstance(choices[0], dict):
        content = (choices[0].get("message") or {}).get("content") or ""
    return content, resp.get("x_directives"), resp.get("x_homepilot")


def get_agent_session(session: Session, workspace_id: str, link_id: str) -> dict[str, Any] | None:
    """The agent's persisted conversation (creating it on first open). Returns
    None when chat is disabled or the agent is unknown."""
    if not feature_enabled(HomePilotFeature.CHAT):
        return None
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return None
    chat = hp_session.resolve_session(session, workspace_id, agent_link_id=link.id, agent_name=link.name)
    row = _get_connection(session, workspace_id, link.connection_id)
    mode = (_secret(row.id).get("chat_mode") if row is not None else None) or "unknown"
    # Failure matrix (A11): when HomePilot is offline / the agent is offline, the
    # conversation is still served from local history — flagged degraded so the UI
    # can say "showing saved history" rather than looking broken.
    degraded = bool(row is None or row.status != "connected" or link.status == "offline")
    return {
        "sessionId": chat.id,
        "agentId": link.id,
        "agentName": link.name,
        "mode": mode,
        "degraded": degraded,
        "messages": hp_session.load_messages(session, chat.id),
    }


def turn(session: Session, workspace_id: str, link_id: str, message: str) -> dict[str, Any]:
    """Send one user turn to a HomePilot persona in propose-only mode and persist
    both sides. The user's message is persisted even when the remote call fails,
    so nothing they typed is lost. HomePilot never acts — any proposed operations
    come back in ``x_directives`` for DayPilot to validate/approve in a later step.
    """
    if not feature_enabled(HomePilotFeature.CHAT):
        return {"code": "chat_disabled"}
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return {"code": "not_found"}
    if not link.enabled:
        return {"code": "agent_disabled"}
    text = (message or "").strip()
    if not text:
        return {"code": "empty"}

    row = _get_connection(session, workspace_id, link.connection_id)
    client = _client_for(row) if row is not None else None
    if client is None:
        return {"code": "not_configured"}

    # Multi-account safety: refuse to chat with an agent bound to a DIFFERENT
    # HomePilot account than the connection is now authenticated as.
    bound = (_secret(row.id).get("account_ref") or "")
    if bound and link.account_ref and link.account_ref != bound:
        return {"code": "account_mismatch"}

    chat = hp_session.resolve_session(session, workspace_id, agent_link_id=link.id, agent_name=link.name)
    user_msg = hp_session.append_turn(session, chat, "user", text)
    # Durably persist the user's turn BEFORE the remote call, so a HomePilot
    # failure (which rolls back the request transaction) can never lose what they
    # typed. expire_on_commit is off, so the ORM objects stay usable afterwards.
    session.commit()
    history = hp_session.history_as_messages(session, chat.id)
    model = link.homepilot_model_id or persona_model_id(link.homepilot_project_id)

    import httpx  # local import: keeps the module importable without httpx at load

    try:
        resp = client.persona_chat(
            model, history, tool_mode=ToolMode.PROPOSE, session_id=chat.remote_session_id
        )
    except httpx.TimeoutException:
        # Timed out — the user's message is retained; the UI shows Retry (A11).
        return {"code": "timeout", "sessionId": chat.id, "userMessage": hp_session.message_dict(user_msg)}
    except httpx.HTTPError:
        # Unreachable / transport error — user's message is retained, offer Retry.
        return {"code": "unreachable", "sessionId": chat.id, "userMessage": hp_session.message_dict(user_msg)}

    content, x_directives, x_homepilot = _parse_persona_response(resp)
    mode = "bridge" if x_homepilot is not None else "chat_only"
    # Persist HomePilot's conversation reference once, then reuse it for continuity
    # across turns/devices (A11). HomePilot owns the conversation; we store only
    # the id. Prefer x_homepilot, fall back to the response id.
    if not chat.remote_conversation_id:
        conv = (x_homepilot or {}).get("conversation_id") if isinstance(x_homepilot, dict) else None
        chat.remote_conversation_id = str(conv or resp.get("id") or "") or None
    # AI-behavior guardrail (A12, §13): strip any tool-call / directive machinery
    # that leaked into the visible reply before it is persisted or shown.
    from daypilot_orchestrator.homepilot import guardrails
    clean = guardrails.sanitize_reply(content)
    sanitized = guardrails.was_sanitized(content, clean)
    content = clean or "(no reply)"

    action: dict[str, Any] = {}
    if x_directives is not None:
        action["x_directives"] = x_directives
    if x_homepilot is not None:
        action["x_homepilot"] = x_homepilot

    assistant_msg = hp_session.append_turn(session, chat, "assistant", content, action or None)

    # Validate the untrusted directives and map them to real work (A7). HomePilot
    # already validated on its side; DayPilot re-validates from scratch (defense
    # in depth) and applies only what survives. External-world proposals become
    # waiting_for_approval tasks + pending approvals — never executed here.
    applied: dict[str, Any] = {}
    if x_directives is not None:
        validation = validate_directives(x_directives)
        result = hp_mapper.apply_directives(session, workspace_id, link, validation)
        applied = result.summary()

    proposals = len(applied.get("approvals") or [])

    # Observability (A12): one audit record per bridge turn with counts only —
    # never the message text, never a secret.
    _audit_bridge_turn(session, workspace_id, link, mode=mode, applied=applied, sanitized=sanitized)

    return {
        "code": "ok",
        "sessionId": chat.id,
        "mode": mode,
        "proposals": proposals,
        "applied": applied,
        "userMessage": hp_session.message_dict(user_msg),
        "reply": hp_session.message_dict(assistant_msg),
    }


def _audit_bridge_turn(session: Session, workspace_id: str, link: HomePilotAgentLink, *, mode: str, applied: dict[str, Any], sanitized: bool) -> None:
    """Metrics/audit for a bridge turn (A12). Counts only — no message text."""
    try:
        from daypilot_knowledge.db import AuditLog

        counts = applied.get("counts") or {}
        session.add(AuditLog(
            event_type="homepilot.bridge.turn",
            risk="low",
            decision=mode,
            payload_json={
                "workspaceId": workspace_id,
                "agentLinkId": link.id,
                "mode": mode,
                "directivesCreated": counts.get("created", 0),
                "approvalsProposed": counts.get("approvals", 0),
                "directivesRejected": counts.get("rejected", 0),
                "delegations": counts.get("delegations", 0),
                "replySanitized": bool(sanitized),
            },
        ))
    except Exception:  # noqa: BLE001 - audit must never break a turn
        pass


def _public_agent_task(t: Task) -> dict[str, Any]:
    rr = t.remote_reference or {}
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "progress": int(t.progress_percent or 0),
        "owner": t.owner,
        "lifecycle": rr.get("lifecycle"),
        "capability": rr.get("capability"),
        "approvalId": t.approval_id,
        "assignedAgentLinkId": t.assigned_agent_link_id,
        "createdAt": t.created_at.isoformat() if t.created_at else None,
        "updatedAt": t.updated_at.isoformat() if t.updated_at else None,
    }


def list_agent_tasks(session: Session, workspace_id: str, link_id: str) -> dict[str, Any] | None:
    """The tasks this agent owns, with lifecycle — surfaced in the workspace."""
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return None
    rows = session.execute(
        select(Task)
        .where(Task.workspace_id == workspace_id, Task.assigned_agent_link_id == link_id)
        .order_by(Task.updated_at.desc())
    ).scalars()
    return {"agentId": link_id, "tasks": [_public_agent_task(t) for t in rows]}


def list_delegations(session: Session, workspace_id: str, link_id: str) -> dict[str, Any] | None:
    """Delegation chains involving this agent (manager or worker). None when the
    agent is unknown."""
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return None
    from daypilot_orchestrator.homepilot import delegation as hp_delegation

    return hp_delegation.list_delegations(session, workspace_id, link_id)


def on_approval_decided(session: Session, approval: Approval) -> dict[str, Any] | None:
    """Hook the Approval Center: once an agent-proposal approval is decided,
    execute it through DayPilot's own integrations (approve) or mark it rejected.
    Returns None for approvals that aren't agent proposals (left untouched)."""
    if approval is None or approval.resource_type != "task" or not approval.resource_id:
        return None
    task = session.get(Task, approval.resource_id)
    if task is None or not task.assigned_agent_link_id:
        return None
    if (task.remote_reference or {}).get("kind") != "action.propose":
        return None
    if approval.status == "approved":
        return hp_actions.execute_approved(session, task.workspace_id, task)
    if approval.status == "rejected":
        return hp_actions.reject(session, task.workspace_id, task, approval.reason)
    return None


def fetch_avatar(session: Session, workspace_id: str, link_id: str) -> tuple[bytes, str] | None:
    """Proxy the persona avatar from HomePilot (the browser never calls it).
    Best-effort — returns None so the UI falls back to initials."""
    link = _get_link(session, workspace_id, link_id)
    if link is None:
        return None
    # Locally-embedded portrait (offline .hpersona import, or a seeded demo agent):
    # serve it directly — there is no live HomePilot to proxy from.
    from daypilot_orchestrator.homepilot.hpersona import decode_avatar_data_uri

    embedded = decode_avatar_data_uri((link.snapshot_json or {}).get("avatar_data_uri"))
    if embedded is not None:
        return embedded
    ref = link.thumbnail_ref or link.avatar_ref
    if not ref:
        return None
    row = _get_connection(session, workspace_id, link.connection_id)
    if row is None:
        return None
    client = _client_for(row)
    if client is None:
        return None
    import httpx

    secret = _secret(row.id)
    base = (secret.get("base_url") or _default_base_url()).rstrip("/")
    # HomePilot serves project assets under /files/<relative-path>.
    url_path = ref if ref.startswith("/") else f"/files/{ref}"
    try:
        with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {secret.get('api_key','')}"}
                          if secret.get("api_key") else {}, timeout=10.0) as c:
            r = c.get(url_path)
        if r.status_code != 200 or not r.content:
            return None
        return r.content, r.headers.get("content-type", "image/webp")
    except (httpx.HTTPError, ValueError):
        return None
