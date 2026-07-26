"""HomePilot agents integration — connection + agent-profile endpoints.

Gated by ``DAYPILOT_HOMEPILOT_RUNTIME_ENABLED``: when the runtime is off, the
whole surface 404s (the integration is inert). The browser reaches HomePilot
ONLY through these DayPilot-owned endpoints.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import Response

from .. import homepilot_platform as hp
from .. import homepilot_setup as hp_setup
from ..db import get_session

router = APIRouter(tags=["homepilot"])


def _require_imports() -> None:
    _require_runtime()
    if not hp.imports_enabled():
        raise HTTPException(status_code=404, detail="HomePilot offline imports are disabled")


def _require_runtime() -> None:
    if not hp.enabled():
        raise HTTPException(status_code=404, detail="HomePilot runtime is disabled")


def _require_chat() -> None:
    from daypilot_orchestrator.homepilot.contracts import HomePilotFeature, feature_enabled

    _require_runtime()
    if not feature_enabled(HomePilotFeature.CHAT):
        raise HTTPException(status_code=404, detail="HomePilot chat is disabled")


class ConnectBody(BaseModel):
    workspaceId: str = "default"
    baseUrl: str | None = None
    apiKey: str | None = None


class SetupTestBody(BaseModel):
    baseUrl: str
    apiKey: str | None = None
    allowPrivate: bool = True


# ---- setup / onboarding -----------------------------------------------------

@router.get("/v1/homepilot/setup/status")
def setup_status(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """Connection-state machine for the settings page + wizard. Always reachable
    (even under an admin lock) so the UI renders the right message, not an error."""
    return hp.setup_status(session, workspaceId)


@router.post("/v1/homepilot/setup/detect")
def setup_detect() -> dict[str, Any]:
    """Look for a HomePilot installation on this host (backend-only probe of a
    fixed candidate list). The browser never probes the network itself."""
    _require_runtime()
    return hp_setup.detect()


@router.post("/v1/homepilot/setup/test")
def setup_test(body: SetupTestBody) -> dict[str, Any]:
    """Run a connection checklist against an address without persisting anything.
    Never echoes the API key back."""
    _require_runtime()
    return hp_setup.test_address(body.baseUrl, body.apiKey, allow_private=body.allowPrivate)


class WsBody(BaseModel):
    workspaceId: str = "default"


class ProfilePatch(BaseModel):
    workspaceId: str = "default"
    enabled: bool | None = None
    favorite: bool | None = None


# ---- connections ------------------------------------------------------------

@router.post("/v1/homepilot/connections")
def create_connection(body: ConnectBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    return hp.connect(session, body.workspaceId, body.baseUrl, body.apiKey)


@router.get("/v1/homepilot/connections")
def list_connections(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    return hp.list_connections(session, workspaceId)


@router.post("/v1/homepilot/connections/{connection_id}/test")
def test_connection(connection_id: str, body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    out = hp.test_connection(session, body.workspaceId, connection_id)
    if out.get("code") == "not_found":
        raise HTTPException(status_code=404, detail="connection_not_found")
    return out


@router.get("/v1/homepilot/connections/{connection_id}/status")
def connection_status(connection_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    out = hp.connection_status(session, workspaceId, connection_id)
    if out.get("code") == "not_found":
        raise HTTPException(status_code=404, detail="connection_not_found")
    return out


class ConnectionPrefsBody(BaseModel):
    workspaceId: str = "default"
    autoSync: bool | None = None
    syncOnStart: bool | None = None
    syncIntervalMinutes: int | None = None
    newAgentsDisabled: bool | None = None
    showOffline: bool | None = None
    useSessions: bool | None = None
    allowDelegation: bool | None = None


@router.patch("/v1/homepilot/connections/{connection_id}")
def patch_connection(connection_id: str, body: ConnectionPrefsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Update a connection's sync + agent-behavior preferences. The permanent
    approval rule is never a preference (external actions always need approval)."""
    _require_runtime()
    prefs = {k: v for k, v in body.model_dump(exclude={"workspaceId"}).items() if v is not None}
    out = hp.patch_connection(session, body.workspaceId, connection_id, prefs)
    if out is None:
        raise HTTPException(status_code=404, detail="connection_not_found")
    return out


@router.delete("/v1/homepilot/connections/{connection_id}")
def delete_connection(connection_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    return hp.delete_connection(session, workspaceId, connection_id)


# ---- add-agent flow (A10) ---------------------------------------------------

@router.get("/v1/homepilot/add-info")
def homepilot_add_info(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """Drives the 'Add agent' screen: gallery URL + whether offline import is on.
    Adding an agent happens in HomePilot; DayPilot only connects and refreshes."""
    _require_runtime()
    return hp.add_info(session, workspaceId)


@router.post("/v1/homepilot/hpersona/preview")
async def hpersona_preview(file: UploadFile = File(...)) -> dict[str, Any]:
    """Offline fallback (behind IMPORTS): validate + preview a .hpersona and
    report its dependencies, without importing anything."""
    _require_imports()
    return hp.hpersona_preview(await file.read())


@router.post("/v1/homepilot/hpersona/import")
async def hpersona_import(workspaceId: str = "default", file: UploadFile = File(...),
                          session: Session = Depends(get_session)) -> dict[str, Any]:
    """Offline fallback (behind IMPORTS): import a .hpersona as a local agent
    reference. The primary path is always HomePilot, not this."""
    _require_imports()
    out = hp.hpersona_import(session, workspaceId, await file.read())
    if out.get("code") == "invalid":
        raise HTTPException(status_code=422, detail={"error": "invalid_hpersona", **out})
    return out


@router.post("/v1/homepilot/connections/{connection_id}/sync")
def sync_connection(connection_id: str, body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    out = hp.sync(session, body.workspaceId, connection_id)
    if out.get("code") == "not_found":
        raise HTTPException(status_code=404, detail="connection_not_found")
    if out.get("code") == "sync_disabled":
        raise HTTPException(status_code=409, detail="sync_disabled")
    return out


# ---- agent profiles ---------------------------------------------------------

@router.get("/v1/agents/profiles")
def list_profiles(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    return hp.list_profiles(session, workspaceId)


@router.get("/v1/agents/profiles/{link_id}")
def get_profile(link_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    out = hp.get_profile(session, workspaceId, link_id)
    if out is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return out


@router.patch("/v1/agents/profiles/{link_id}")
def patch_profile(link_id: str, body: ProfilePatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_runtime()
    patch = {k: v for k, v in (("enabled", body.enabled), ("favorite", body.favorite)) if v is not None}
    out = hp.patch_profile(session, body.workspaceId, link_id, patch)
    if out is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return out


@router.get("/v1/agents/profiles/{link_id}/avatar")
def get_avatar(link_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> Response:
    _require_runtime()
    result = hp.fetch_avatar(session, workspaceId, link_id)
    if result is None:
        # No avatar — the UI falls back to initials.
        return Response(status_code=204)
    content, content_type = result
    return Response(content=content, media_type=content_type)


# ---- agent chat (A6) --------------------------------------------------------

class TurnBody(BaseModel):
    workspaceId: str = "default"
    message: str = ""


@router.get("/v1/agents/profiles/{link_id}/session")
def get_agent_session(link_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """The agent's persisted conversation (created on first open)."""
    _require_chat()
    out = hp.get_agent_session(session, workspaceId, link_id)
    if out is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return out


@router.get("/v1/agents/profiles/{link_id}/tasks")
def get_agent_tasks(link_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """The agent's tasks with their approval lifecycle, for the workspace panel."""
    _require_runtime()
    out = hp.list_agent_tasks(session, workspaceId, link_id)
    if out is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return out


@router.get("/v1/agents/profiles/{link_id}/delegations")
def get_agent_delegations(link_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    """Delegation chains (You → manager → worker) involving this agent."""
    _require_runtime()
    out = hp.list_delegations(session, workspaceId, link_id)
    if out is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return out


@router.post("/v1/agents/profiles/{link_id}/turn")
def agent_turn(link_id: str, body: TurnBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Send one user message to the agent's persona (always propose-only) and
    persist both sides. Returns the reply plus how many operations were proposed."""
    _require_chat()
    out = hp.turn(session, body.workspaceId, link_id, body.message)
    code = out.get("code")
    if code == "not_found":
        raise HTTPException(status_code=404, detail="agent_not_found")
    if code == "agent_disabled":
        raise HTTPException(status_code=409, detail="agent_disabled")
    if code == "account_mismatch":
        raise HTTPException(status_code=409, detail="account_mismatch")
    if code == "empty":
        raise HTTPException(status_code=422, detail="empty_message")
    if code == "not_configured":
        raise HTTPException(status_code=409, detail="homepilot_not_configured")
    if code == "timeout":
        # The user's message was persisted; the client shows Retry (A11).
        raise HTTPException(status_code=504, detail={"error": "homepilot_timeout", **out})
    if code == "unreachable":
        # The user's message was persisted; tell the client to retry.
        raise HTTPException(status_code=502, detail={"error": "homepilot_unreachable", **out})
    return out
