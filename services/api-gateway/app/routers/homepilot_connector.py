"""HomePilot connector API — see ``app/homepilot_connector.py`` and
``docs/homepilot-connector.md``.

Two audiences, two kinds of authentication:

* **HomePilot's server** (``/v1/integrations/homepilot/…``) — a scoped grant
  token (``Authorization: Bearer dph_…``), except the pairing request and
  exchange, which are protected by PKCE.
* **The DayPilot user** (``/v1/integrations/homepilot/consent/…`` and
  ``/grants``) — their signed-in DayPilot session cookie, with the CSRF
  header on every write.

Workspace ids are never accepted as authorisation on this surface.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import homepilot_connector as hc
from .. import identity
from ..db import get_session

router = APIRouter(prefix="/v1/integrations/homepilot", tags=["homepilot-connector"])


def _enabled() -> None:
    if not hc.connector_enabled():
        raise HTTPException(status_code=404, detail="The HomePilot connector is disabled")


def _raise(exc: hc.ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": exc.code, "message": str(exc)})


def _grant(session: Session, authorization: str | None) -> hc.GrantPrincipal:
    try:
        return hc.authenticate(session, authorization)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


def _signed_in(session: Session, dp_session: str | None):
    resolved = identity.resolve_session(session, dp_session)
    if resolved is None:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated",
                                                     "message": "Sign in to DayPilot first."})
    return resolved


def _csrf(auth_session: Any, token: str | None) -> None:
    if not token or token != auth_session.csrf_token:
        raise HTTPException(status_code=403, detail={"error": "csrf_failed", "message": "CSRF check failed."})


# ── bodies ───────────────────────────────────────────────────────────────────

class PairingStart(BaseModel):
    clientName: str = Field("HomePilot", max_length=120)
    accountRef: str = Field("", max_length=200)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    codeChallenge: str = Field(..., max_length=128)
    codeChallengeMethod: str = "S256"


class PairingExchange(BaseModel):
    codeVerifier: str = Field(..., max_length=128)


class ConsentDecision(BaseModel):
    approve: bool
    workspaceId: str = Field("", max_length=36)
    scopes: list[str] | None = Field(None, max_length=20)


class ProposalBody(BaseModel):
    capability: str = Field(..., max_length=80)
    title: str = Field(..., max_length=400)
    detail: str = Field("", max_length=8000)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotencyKey: str = Field(..., min_length=8, max_length=128)
    origin: dict[str, Any] = Field(default_factory=dict)


# ── HomePilot server ─────────────────────────────────────────────────────────

@router.get("/manifest")
def get_manifest(authorization: str | None = Header(default=None),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    """Versioned capability manifest. Public without a token (what is supported);
    with a valid token it also reports what this connection may use."""
    _enabled()
    principal = None
    if authorization:
        principal = _grant(session, authorization)
    return hc.manifest(principal)


@router.post("/pairings", status_code=201)
def start_pairing(body: PairingStart, session: Session = Depends(get_session)) -> dict[str, Any]:
    _enabled()
    try:
        return hc.start_pairing(session, client_name=body.clientName, account_ref=body.accountRef,
                                scopes=body.scopes, code_challenge=body.codeChallenge,
                                method=body.codeChallengeMethod)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.post("/pairings/{pairing_id}/token")
def exchange(pairing_id: str, body: PairingExchange, session: Session = Depends(get_session)) -> dict[str, Any]:
    _enabled()
    try:
        return hc.exchange_pairing(session, pairing_id, body.codeVerifier)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.get("/account")
def get_account(authorization: str | None = Header(default=None),
                session: Session = Depends(get_session)) -> dict[str, Any]:
    _enabled()
    return hc.account(session, _grant(session, authorization))


@router.get("/context")
def get_context(include: str = "", limit: int = 10, authorization: str | None = Header(default=None),
                session: Session = Depends(get_session)) -> dict[str, Any]:
    """Aggregate, read-only workday context limited to the granted scopes."""
    _enabled()
    principal = _grant(session, authorization)
    parts = [p.strip() for p in include.split(",") if p.strip()] or None
    return hc.context(session, principal, parts, limit)


@router.post("/proposals", status_code=201)
def create_proposal(body: ProposalBody, authorization: str | None = Header(default=None),
                    x_daypilot_hop: int = Header(default=0, alias="X-DayPilot-Hop"),
                    session: Session = Depends(get_session)) -> dict[str, Any]:
    _enabled()
    principal = _grant(session, authorization)
    try:
        return hc.propose(session, principal, body.model_dump(), hop=x_daypilot_hop)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, authorization: str | None = Header(default=None),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    _enabled()
    principal = _grant(session, authorization)
    try:
        return hc.proposal_status(session, principal, proposal_id)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.delete("/grant")
def revoke_own_grant(authorization: str | None = Header(default=None),
                     session: Session = Depends(get_session)) -> dict[str, Any]:
    """HomePilot calls this when the user disconnects there."""
    _enabled()
    principal = _grant(session, authorization)
    hc.revoke(session, principal.grant, by_user_id=None, via="homepilot")
    return {"revoked": True}


# ── DayPilot user (consent + management) ─────────────────────────────────────

@router.get("/consent/{user_code}")
def consent_info(user_code: str, session: Session = Depends(get_session),
                 dp_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    _enabled()
    user, _ = _signed_in(session, dp_session)
    try:
        return hc.describe_pairing(session, user_code, user.id)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.post("/consent/{user_code}")
def consent_decide(user_code: str, body: ConsentDecision, session: Session = Depends(get_session),
                   dp_session: str | None = Cookie(default=None),
                   x_csrf_token: str | None = Header(default=None)) -> dict[str, Any]:
    _enabled()
    user, auth_session = _signed_in(session, dp_session)
    _csrf(auth_session, x_csrf_token)
    try:
        return hc.decide_pairing(session, user_code, user, approve=body.approve,
                                 workspace_id=body.workspaceId, scopes=body.scopes)
    except hc.ConnectorError as exc:
        raise _raise(exc) from exc


@router.get("/grants")
def my_grants(session: Session = Depends(get_session),
              dp_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    _enabled()
    user, _ = _signed_in(session, dp_session)
    return {"grants": hc.list_user_grants(session, user.id)}


@router.delete("/grants/{grant_id}")
def revoke_grant(grant_id: str, session: Session = Depends(get_session),
                 dp_session: str | None = Cookie(default=None),
                 x_csrf_token: str | None = Header(default=None)) -> dict[str, Any]:
    _enabled()
    user, auth_session = _signed_in(session, dp_session)
    _csrf(auth_session, x_csrf_token)
    from daypilot_knowledge.db import HomePilotGrant
    grant = session.get(HomePilotGrant, grant_id)
    if grant is None or grant.user_id != user.id:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such connection."})
    hc.revoke(session, grant, by_user_id=user.id, via="daypilot")
    return {"revoked": True}
