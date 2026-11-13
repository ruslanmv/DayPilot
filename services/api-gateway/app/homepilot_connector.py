"""HomePilot connector — the HomePilot-facing DayPilot API (contract v1).

The reverse direction of the existing runtime bridge: there, DayPilot reads
HomePilot personas; here, a HomePilot account reads the workday a DayPilot user
has explicitly authorised, and proposes actions that DayPilot governs.

Ownership rule (unchanged): HomePilot owns persona intelligence; DayPilot owns
workday operations and approval-governed execution. Nothing here copies
persona memory into DayPilot, and HomePilot never executes a DayPilot action.

Security model
--------------
* **Pairing** (device flow + PKCE). HomePilot's *server* asks for access with
  an S256 ``code_challenge``; the DayPilot user approves it while signed in to
  DayPilot, picking one workspace they are a member of and the scopes to grant;
  HomePilot exchanges the request, once, with the ``code_verifier`` for a grant
  token. A pairing expires after 10 minutes.
* **Grant** — a scoped integration identity (``dph_…`` bearer token; only its
  SHA-256 is stored). Every request re-derives the workspace from the grant and
  re-checks that the user is still an active member. **A workspace id sent by
  the caller is never used for authorisation.**
* **Scopes** limit every read and the proposal endpoint. Revocation is
  immediate (user side or HomePilot side); expiry is optional.
* **Audit** — pairing, grant issue, revocation, reads and proposals are
  written to ``audit_logs``.

Weather and wellness exist only in the browser (Open-Meteo is called from the
user's browser and wellness state lives in ``localStorage``), so the manifest
reports them as ``ui_only`` and there is no API that pretends to sync them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    Approval,
    AuditLog,
    CalendarEvent,
    DayPlan,
    Event,
    HomePilotGrant,
    HomePilotPairing,
    HomePilotProposal,
    Project,
    Task,
    User,
    WorkspaceMembership,
)
from daypilot_knowledge.db.models import utcnow

CONTRACT_VERSION = "1"
TOKEN_PREFIX = "dph_"
PAIRING_TTL = timedelta(minutes=10)
MAX_HOPS = 3
_USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"

#: scope -> what it allows. ``wellness.read`` is reserved: never grantable while
#: wellness data exists only in the browser.
SCOPES: dict[str, str] = {
    "plan.read": "Today's plan, the current focus block and the daily standup draft",
    "tasks.read": "Your open tasks",
    "projects.read": "Operational projects: status, risk, next human action",
    "calendar.read": "Today's and upcoming calendar events",
    "approvals.read": "Pending approvals waiting for you",
    "notifications.read": "Recent notifications",
    "actions.propose": "Ask DayPilot to prepare actions — DayPilot decides and you approve",
}
GRANTABLE_SCOPES = frozenset(SCOPES)
RESERVED_SCOPES = frozenset({"wellness.read"})

#: Feature manifest: feature -> (scope it needs, backend data available?)
FEATURES: dict[str, dict[str, Any]] = {
    "today_plan": {"scope": "plan.read", "kind": "data"},
    "focus": {"scope": "plan.read", "kind": "data"},
    "daily_standup": {"scope": "plan.read", "kind": "data"},
    "tasks": {"scope": "tasks.read", "kind": "data"},
    "projects": {"scope": "projects.read", "kind": "data"},
    "calendar": {"scope": "calendar.read", "kind": "data"},
    "approvals": {"scope": "approvals.read", "kind": "data"},
    "notifications": {"scope": "notifications.read", "kind": "data"},
    "action_proposals": {"scope": "actions.propose", "kind": "action"},
    # Browser-only views: never synchronised, never exposed as data.
    "weather": {"scope": None, "kind": "ui_only",
                "note": "Shown in DayPilot's Weather view; data stays in the browser."},
    "wellness": {"scope": "wellness.read", "kind": "ui_only",
                 "note": "Screen-break reminders run in the browser; nothing is synchronised."},
}

#: What HomePilot may ask DayPilot to prepare, and DayPilot's policy for each.
#: Every proposal becomes a DayPilot task waiting for approval; DayPilot's own
#: Approval Center decides, and DayPilot's own integrations execute. Anything
#: not listed — sending messages directly, code or finance changes, deletions —
#: is refused.
PROPOSAL_POLICY: dict[str, dict[str, str]] = {
    "task.create": {"risk": "low", "approval": "required"},
    "task.update": {"risk": "low", "approval": "required"},
    "project.update": {"risk": "low", "approval": "required"},
    "calendar.create": {"risk": "low", "approval": "required"},
    "calendar.update": {"risk": "medium", "approval": "required"},
    "document.generate": {"risk": "low", "approval": "required"},
}
MAX_TITLE = 200
MAX_DETAIL = 4000
MAX_ARGS_BYTES = 8 * 1024


class ConnectorError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


# ── small helpers ────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _now() -> datetime:
    return datetime.utcnow()


def _audit(session: Session, event: str, *, user_id: str | None, payload: dict[str, Any],
           decision: str = "recorded", risk: str = "low") -> None:
    session.add(AuditLog(actor_user_id=user_id, event_type=f"homepilot.connector.{event}",
                         risk=risk, decision=decision, payload_json=payload))


def _clean_scopes(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for s in raw:
        s = str(s).strip()
        if s in GRANTABLE_SCOPES and s not in out:
            out.append(s)
    return out


def _user_code() -> str:
    raw = "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def pkce_challenge(verifier: str) -> str:
    """RFC 7636 S256."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


_PKCE_RE = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9\-_]{43}$")


# ── pairing ──────────────────────────────────────────────────────────────────

def start_pairing(session: Session, *, client_name: str, account_ref: str,
                  scopes: Any, code_challenge: str, method: str = "S256") -> dict[str, Any]:
    if method != "S256" or not _CHALLENGE_RE.match(code_challenge or ""):
        raise ConnectorError(400, "invalid_request", "A PKCE S256 code_challenge is required.")
    requested = _clean_scopes(scopes) or ["plan.read", "tasks.read"]
    pairing = HomePilotPairing(
        user_code=_user_code(), client_name=(client_name or "HomePilot")[:120],
        client_account_ref=(account_ref or "")[:200], requested_scopes=requested,
        code_challenge=code_challenge, status="pending", granted_scopes=[],
        expires_at=_now() + PAIRING_TTL,
    )
    session.add(pairing)
    session.flush()
    _audit(session, "pairing.requested", user_id=None,
           payload={"pairingId": pairing.id, "client": pairing.client_name, "scopes": requested})
    return {
        "pairingId": pairing.id,
        "userCode": pairing.user_code,
        "verificationPath": f"/#/connect/homepilot?code={pairing.user_code}",
        "expiresIn": int(PAIRING_TTL.total_seconds()),
        "interval": 3,
        "requestedScopes": requested,
    }


def _pending_by_code(session: Session, user_code: str) -> HomePilotPairing:
    row = session.execute(select(HomePilotPairing).where(
        HomePilotPairing.user_code == (user_code or "").strip().upper())).scalar_one_or_none()
    if row is None or row.status != "pending" or _naive(row.expires_at) < _now():
        raise ConnectorError(404, "not_found", "This connection request is not valid or has expired.")
    return row


def describe_pairing(session: Session, user_code: str, user_id: str) -> dict[str, Any]:
    """What the consent screen shows, plus the workspaces this user may grant."""
    row = _pending_by_code(session, user_code)
    memberships = session.execute(select(WorkspaceMembership).where(
        WorkspaceMembership.user_id == user_id)).scalars().all()
    return {
        "client": row.client_name,
        "accountRef": row.client_account_ref,
        "requestedScopes": [{"scope": s, "description": SCOPES[s]} for s in row.requested_scopes],
        "workspaces": [{"id": m.workspace_id, "role": m.role} for m in memberships],
        "expiresAt": _naive(row.expires_at).isoformat() + "Z",
    }


def decide_pairing(session: Session, user_code: str, user: User, *, approve: bool,
                   workspace_id: str = "", scopes: Any = None) -> dict[str, Any]:
    row = _pending_by_code(session, user_code)
    if not approve:
        row.status = "denied"
        _audit(session, "pairing.denied", user_id=user.id, payload={"pairingId": row.id})
        return {"status": "denied"}
    membership = session.execute(select(WorkspaceMembership).where(
        WorkspaceMembership.user_id == user.id,
        WorkspaceMembership.workspace_id == workspace_id)).scalar_one_or_none()
    if membership is None:
        # The workspace comes from the user's own memberships, never the request.
        raise ConnectorError(403, "not_a_member", "You are not a member of that workspace.")
    granted = [s for s in _clean_scopes(scopes if scopes is not None else row.requested_scopes)
               if s in row.requested_scopes]
    if membership.role == "read_only":
        granted = [s for s in granted if s != "actions.propose"]
    if not granted:
        raise ConnectorError(400, "no_scopes", "Grant at least one permission.")
    row.status = "approved"
    row.approved_by_user_id = user.id
    row.workspace_id = workspace_id
    row.granted_scopes = granted
    _audit(session, "pairing.approved", user_id=user.id,
           payload={"pairingId": row.id, "workspaceId": workspace_id, "scopes": granted})
    return {"status": "approved", "scopes": granted, "workspaceId": workspace_id}


def exchange_pairing(session: Session, pairing_id: str, code_verifier: str) -> dict[str, Any]:
    """HomePilot's server polls this. Returns the token exactly once."""
    row = session.get(HomePilotPairing, pairing_id)
    if row is None or _naive(row.expires_at) < _now():
        raise ConnectorError(400, "expired_token", "The connection request expired. Start again.")
    if not _PKCE_RE.match(code_verifier or "") or not hmac.compare_digest(
            pkce_challenge(code_verifier), row.code_challenge):
        raise ConnectorError(400, "invalid_grant", "The code verifier does not match.")
    if row.status == "pending":
        raise ConnectorError(400, "authorization_pending", "Waiting for the user to approve in DayPilot.")
    if row.status == "denied":
        raise ConnectorError(400, "access_denied", "The user declined the connection.")
    if row.status != "approved":
        raise ConnectorError(400, "invalid_grant", "This connection request was already used.")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    grant = HomePilotGrant(
        token_hash=_sha256(token), token_hint=token[:8], user_id=row.approved_by_user_id,
        workspace_id=row.workspace_id, scopes=list(row.granted_scopes),
        client_name=row.client_name, client_account_ref=row.client_account_ref,
    )
    session.add(grant)
    row.status = "consumed"
    session.flush()
    _audit(session, "grant.issued", user_id=grant.user_id,
           payload={"grantId": grant.id, "workspaceId": grant.workspace_id, "scopes": grant.scopes})
    return {"accessToken": token, "tokenType": "Bearer", "grantId": grant.id,
            "scopes": grant.scopes, "contractVersion": CONTRACT_VERSION}


# ── authenticating a grant ───────────────────────────────────────────────────

class GrantPrincipal:
    def __init__(self, grant: HomePilotGrant, user: User, role: str) -> None:
        self.grant = grant
        self.user = user
        self.role = role
        self.workspace_id = grant.workspace_id
        self.scopes = frozenset(grant.scopes or [])

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise ConnectorError(403, "insufficient_scope", f"This connection was not granted '{scope}'.")


def authenticate(session: Session, authorization: str | None) -> GrantPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ConnectorError(401, "invalid_token", "A DayPilot connection token is required.")
    token = authorization.split(" ", 1)[1].strip()
    if not token.startswith(TOKEN_PREFIX):
        raise ConnectorError(401, "invalid_token", "Not a DayPilot connection token.")
    grant = session.execute(select(HomePilotGrant).where(
        HomePilotGrant.token_hash == _sha256(token))).scalar_one_or_none()
    if grant is None or grant.revoked_at is not None:
        raise ConnectorError(401, "invalid_token", "This connection was revoked or does not exist.")
    if grant.expires_at is not None and _naive(grant.expires_at) < _now():
        raise ConnectorError(401, "invalid_token", "This connection has expired.")
    user = session.get(User, grant.user_id)
    if user is None or user.status != "active":
        raise ConnectorError(401, "invalid_token", "The DayPilot account is not active.")
    membership = session.execute(select(WorkspaceMembership).where(
        WorkspaceMembership.user_id == grant.user_id,
        WorkspaceMembership.workspace_id == grant.workspace_id)).scalar_one_or_none()
    if membership is None:
        raise ConnectorError(403, "membership_revoked",
                             "The DayPilot account no longer has access to this workspace.")
    grant.last_used_at = utcnow()
    return GrantPrincipal(grant, user, membership.role)


def revoke(session: Session, grant: HomePilotGrant, *, by_user_id: str | None, via: str) -> None:
    if grant.revoked_at is None:
        grant.revoked_at = utcnow()
        _audit(session, "grant.revoked", user_id=by_user_id,
               payload={"grantId": grant.id, "via": via}, decision="revoked")


def list_user_grants(session: Session, user_id: str) -> list[dict[str, Any]]:
    rows = session.execute(select(HomePilotGrant).where(
        HomePilotGrant.user_id == user_id, HomePilotGrant.revoked_at.is_(None))).scalars().all()
    return [{
        "id": g.id, "client": g.client_name, "accountRef": g.client_account_ref,
        "workspaceId": g.workspace_id, "scopes": g.scopes,
        "createdAt": _naive(g.created_at).isoformat() + "Z" if g.created_at else None,
        "lastUsedAt": _naive(g.last_used_at).isoformat() + "Z" if g.last_used_at else None,
    } for g in rows]


# ── discovery ────────────────────────────────────────────────────────────────

def manifest(principal: GrantPrincipal | None) -> dict[str, Any]:
    """Versioned capability manifest. Without a token: what this DayPilot
    supports. With one: also what this connection is authorised for."""
    features = {}
    for name, spec in FEATURES.items():
        supported = spec["kind"] in ("data", "action")
        authorized = bool(principal and spec["scope"] and spec["scope"] in principal.scopes)
        features[name] = {
            "kind": spec["kind"],
            "supported": supported,
            "enabled": supported,
            "scope": spec["scope"],
            "authorized": authorized if supported else False,
            "available": bool(supported and authorized),
            **({"note": spec["note"]} if spec.get("note") else {}),
        }
    return {
        "object": "daypilot.manifest",
        "contractVersion": CONTRACT_VERSION,
        "service": "daypilot",
        "features": features,
        "scopes": {s: d for s, d in SCOPES.items()},
        "proposalCapabilities": {k: dict(v) for k, v in PROPOSAL_POLICY.items()},
        "limits": {"maxHops": MAX_HOPS, "maxTitle": MAX_TITLE, "maxDetail": MAX_DETAIL},
        "views": {
            "today": "/#/today", "tasks": "/#/tasks", "calendar": "/#/calendar",
            "projects": "/#/projects", "approvals": "/#/approvals",
            "weather": "/#/weather", "wellness": "/#/wellness",
        },
    }


def account(session: Session, principal: GrantPrincipal) -> dict[str, Any]:
    from daypilot_knowledge.db import Workspace
    ws = session.get(Workspace, principal.workspace_id)
    return {
        "user": {"displayName": principal.user.display_name},
        "workspace": {"id": principal.workspace_id, "name": ws.name if ws else principal.workspace_id,
                      "role": principal.role},
        "scopes": sorted(principal.scopes),
        "grantId": principal.grant.id,
        "contractVersion": CONTRACT_VERSION,
    }


# ── read-only workday context ────────────────────────────────────────────────

_OPEN_TASK_STATES = ("active", "planned", "waiting_for_input", "blocked", "in_progress", "todo")
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _iso(dt: datetime | None) -> str | None:
    return (_naive(dt).isoformat() + "Z") if dt else None


def context(session: Session, principal: GrantPrincipal, include: list[str] | None = None,
            limit: int = 10) -> dict[str, Any]:
    """One aggregate read for everything this connection may see.

    Sections the grant does not cover are reported as ``not_authorized`` —
    never silently empty, so HomePilot can show the right state."""
    ws = principal.workspace_id
    limit = max(1, min(int(limit or 10), 25))
    wanted = set(include or ["plan", "tasks", "projects", "calendar", "approvals", "notifications"])
    out: dict[str, Any] = {"workspaceId": ws, "generatedAt": _iso(utcnow()),
                           "contractVersion": CONTRACT_VERSION, "sections": {}}
    today = datetime.utcnow().date().isoformat()

    def section(name: str, scope: str, build) -> None:
        if name not in wanted:
            return
        if scope not in principal.scopes:
            out["sections"][name] = {"status": "not_authorized"}
            return
        out["sections"][name] = {"status": "ok", **build()}

    def plan():
        dp = session.execute(select(DayPlan).where(DayPlan.workspace_id == ws, DayPlan.plan_date == today)
                             .order_by(DayPlan.updated_at.desc())).scalars().first()
        blocks = sorted(dp.blocks, key=lambda b: b.order_index)[:limit] if dp else []
        now_hm = datetime.utcnow().strftime("%H:%M")
        current = next((b for b in blocks if (b.start_time or "") <= now_hm <= (b.end_time or "99:99")), None)
        upcoming = next((b for b in blocks if (b.start_time or "") > now_hm), None)
        from daypilot_knowledge.db import StandupDraft
        standup = session.execute(select(StandupDraft).where(StandupDraft.workspace_id == ws)
                                  .order_by(StandupDraft.reporting_date.desc())).scalars().first()

        def block(b):
            return {"title": b.title, "start": b.start_time, "end": b.end_time, "status": b.status}
        return {
            "date": today,
            "state": dp.state if dp else None,
            "summary": (dp.summary or "")[:500] if dp else "",
            "blocks": [block(b) for b in blocks],
            "focus": block(current) if current else None,
            "nextBlock": block(upcoming) if upcoming else None,
            "standup": {"reportingDate": standup.reporting_date, "status": standup.status,
                        "today": (standup.today_text or "")[:500]} if standup else None,
        }

    def tasks():
        rows = session.execute(select(Task).where(Task.workspace_id == ws,
                                                  Task.status.in_(_OPEN_TASK_STATES))
                               .order_by(Task.due_date.is_(None), Task.due_date, Task.updated_at.desc())
                               .limit(limit * 3)).scalars().all()
        rows = sorted(rows, key=lambda t: (_PRIORITY_RANK.get(t.priority or "medium", 2),
                                           t.due_date is None, _naive(t.due_date) or datetime.max))[:limit]
        return {"items": [{"id": t.id, "title": t.title, "priority": t.priority, "status": t.status,
                           "due": _iso(t.due_date), "projectId": t.project_id,
                           "nextAction": (t.next_action or "")[:300]} for t in rows]}

    def projects():
        rows = session.execute(select(Project).where(Project.workspace_id == ws,
                                                     Project.status != "Archived")
                               .order_by(Project.updated_at.desc()).limit(limit)).scalars().all()
        return {"items": [{"id": p.id, "name": p.name, "status": p.status, "risk": p.risk,
                           "progress": p.progress, "due": _iso(p.due_date),
                           "nextHumanAction": (p.next_human_action or "")[:300]} for p in rows]}

    def calendar():
        start = datetime.utcnow() - timedelta(hours=1)
        end = datetime.utcnow() + timedelta(days=2)
        rows = session.execute(select(CalendarEvent).where(
            CalendarEvent.workspace_id == ws, CalendarEvent.start_at >= start,
            CalendarEvent.start_at <= end, CalendarEvent.status != "cancelled")
            .order_by(CalendarEvent.start_at).limit(limit * 2)).scalars().all()
        items = [{"id": e.id, "title": e.title, "start": _iso(e.start_at), "end": _iso(e.end_at),
                  "status": e.status} for e in rows][:limit]
        conflicts = []
        for a, b in zip(rows, rows[1:]):
            if a.end_at and b.start_at and _naive(b.start_at) < _naive(a.end_at):
                conflicts.append({"first": a.title, "second": b.title, "at": _iso(b.start_at)})
        return {"items": items, "conflicts": conflicts[:5]}

    def approvals():
        rows = session.execute(select(Approval).where(Approval.workspace_id == ws,
                                                      Approval.status == "pending")
                               .order_by(Approval.created_at.desc()).limit(limit)).scalars().all()
        return {"pending": len(rows),
                "items": [{"id": a.id, "action": a.action, "summary": (a.summary or "")[:300],
                           "risk": a.risk, "createdAt": _iso(a.created_at)} for a in rows]}

    def notifications():
        from daypilot_orchestrator.integrations.notifications import NOTIFICATION_EVENT
        rows = session.execute(select(Event).where(Event.workspace_id == ws,
                                                   Event.type == NOTIFICATION_EVENT)
                               .order_by(Event.seq.desc()).limit(limit)).scalars().all()
        return {"items": [{"id": e.id, "severity": (e.payload_json or {}).get("severity", "info"),
                           "title": str((e.payload_json or {}).get("title")
                                        or (e.payload_json or {}).get("type") or "")[:200]}
                          for e in rows]}

    section("plan", "plan.read", plan)
    section("tasks", "tasks.read", tasks)
    section("projects", "projects.read", projects)
    section("calendar", "calendar.read", calendar)
    section("approvals", "approvals.read", approvals)
    section("notifications", "notifications.read", notifications)
    _audit(session, "context.read", user_id=principal.user.id,
           payload={"grantId": principal.grant.id, "sections": sorted(out["sections"])})
    return out


# ── proposals ────────────────────────────────────────────────────────────────

def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", "")
    return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()[:limit]


def propose(session: Session, principal: GrantPrincipal, body: dict[str, Any], *,
            hop: int = 0) -> dict[str, Any]:
    """Prepare an action through DayPilot's own governance. Nothing executes.

    DayPilot validates the capability against its policy, records a task that
    waits for approval and a pending Approval in the Approval Center, and
    returns a durable id. The same idempotency key returns the same proposal."""
    principal.require("actions.propose")
    if principal.role == "read_only":
        raise ConnectorError(403, "read_only", "Your DayPilot role cannot propose actions.")
    if hop >= MAX_HOPS:
        raise ConnectorError(508, "loop_detected", "This request has been forwarded too many times.")
    origin = body.get("origin") or {}
    if str(origin.get("system") or "homepilot").lower() == "daypilot":
        raise ConnectorError(508, "loop_detected", "A DayPilot-originated request cannot be proposed back.")
    key = _clean_text(body.get("idempotencyKey"), 128)
    if not key:
        raise ConnectorError(400, "invalid_request", "An idempotencyKey is required.")
    existing = session.execute(select(HomePilotProposal).where(
        HomePilotProposal.grant_id == principal.grant.id,
        HomePilotProposal.idempotency_key == key)).scalar_one_or_none()
    if existing is not None:
        return proposal_status(session, principal, existing.id) | {"duplicate": True}

    capability = _clean_text(body.get("capability"), 80)
    policy = PROPOSAL_POLICY.get(capability)
    if policy is None:
        _audit(session, "proposal.refused", user_id=principal.user.id, decision="refused",
               payload={"grantId": principal.grant.id, "capability": capability})
        raise ConnectorError(422, "capability_not_allowed",
                             f"DayPilot does not accept '{capability}' from HomePilot.")
    title = _clean_text(body.get("title"), MAX_TITLE)
    if not title:
        raise ConnectorError(400, "invalid_request", "A title is required.")
    detail = _clean_text(body.get("detail"), MAX_DETAIL)
    arguments = body.get("arguments") or {}
    if not isinstance(arguments, dict) or len(json.dumps(arguments, default=str)) > MAX_ARGS_BYTES:
        raise ConnectorError(400, "invalid_request", "arguments must be a small JSON object.")
    origin_ref = _clean_text(origin.get("ref"), 200)

    task = Task(
        workspace_id=principal.workspace_id, title=title, owner="you",
        executor=principal.grant.client_name, priority="medium",
        status="waiting_for_approval", context=detail or None,
        source=f"homepilot-connector:{principal.grant.id}", risk=policy["risk"], progress_percent=0,
        remote_reference={"kind": "action.propose", "capability": capability, "arguments": arguments,
                          "lifecycle": "awaiting", "origin": {"system": "homepilot", "ref": origin_ref,
                                                              "grantId": principal.grant.id}},
    )
    session.add(task)
    session.flush()
    approval = Approval(
        workspace_id=principal.workspace_id, action=capability, summary=title, risk=policy["risk"],
        status="pending", resource_type="task", resource_id=task.id,
        reason=f"Proposed from {principal.grant.client_name}",
    )
    session.add(approval)
    session.flush()
    task.approval_id = approval.id
    row = HomePilotProposal(grant_id=principal.grant.id, workspace_id=principal.workspace_id,
                            idempotency_key=key, origin_ref=origin_ref, capability=capability,
                            task_id=task.id, approval_id=approval.id, status="awaiting")
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        # A concurrent duplicate won the race; return the stored one.
        session.rollback()
        existing = session.execute(select(HomePilotProposal).where(
            HomePilotProposal.grant_id == principal.grant.id,
            HomePilotProposal.idempotency_key == key)).scalar_one()
        return proposal_status(session, principal, existing.id) | {"duplicate": True}
    _audit(session, "proposal.created", user_id=principal.user.id, risk=policy["risk"],
           payload={"grantId": principal.grant.id, "proposalId": row.id, "capability": capability,
                    "taskId": task.id, "approvalId": approval.id})
    return proposal_status(session, principal, row.id) | {"duplicate": False}


def proposal_status(session: Session, principal: GrantPrincipal, proposal_id: str) -> dict[str, Any]:
    row = session.get(HomePilotProposal, proposal_id)
    if row is None or row.grant_id != principal.grant.id:
        raise ConnectorError(404, "not_found", "No such proposal.")
    task = session.get(Task, row.task_id) if row.task_id else None
    approval = session.get(Approval, row.approval_id) if row.approval_id else None
    lifecycle = ((task.remote_reference or {}).get("lifecycle") if task else None) or row.status
    if approval is not None and approval.status in ("rejected", "denied"):
        lifecycle = "rejected"
    return {
        "id": row.id, "capability": row.capability, "status": lifecycle,
        "approval": {"id": approval.id, "status": approval.status,
                     "decidedAt": _iso(approval.decided_at)} if approval else None,
        "approvalRequired": PROPOSAL_POLICY.get(row.capability, {}).get("approval") == "required",
        "taskId": row.task_id, "createdAt": _iso(row.created_at),
        "view": f"/#/approvals?id={row.approval_id}" if row.approval_id else "/#/approvals",
    }


# ── executors for approved internal changes ──────────────────────────────────
#
# Approved HomePilot proposals run through DayPilot's existing lifecycle
# (``homepilot.action_mapping.execute_approved``). calendar.* and
# document.generate use DayPilot's own integration executors; the internal
# changes below are carried out here, inside the proposal's own workspace only.

_TASK_FIELDS = {"title": MAX_TITLE, "priority": 20, "next_action": 1000, "context": MAX_DETAIL}
_PROJECT_FIELDS = {"next_human_action": 1000, "status": 40, "risk": 20}
_registered = False


def _exec_task_create(session: Session, workspace_id: str, task: Task, args: dict[str, Any]) -> tuple[bool, str]:
    priority = str(args.get("priority") or "medium")
    if priority not in ("low", "medium", "high", "critical"):
        priority = "medium"
    new = Task(workspace_id=workspace_id, title=task.title, owner="you", priority=priority,
               status="active", context=task.context, source=task.source,
               project_id=_own_project(session, workspace_id, args.get("project_id")))
    session.add(new)
    session.flush()
    return True, f"Task created: {new.id}"


def _own_project(session: Session, workspace_id: str, project_id: Any) -> str | None:
    if not project_id:
        return None
    p = session.get(Project, str(project_id))
    return p.id if p is not None and p.workspace_id == workspace_id else None


def _exec_task_update(session: Session, workspace_id: str, task: Task, args: dict[str, Any]) -> tuple[bool, str]:
    target = session.get(Task, str(args.get("task_id") or ""))
    if target is None or target.workspace_id != workspace_id:
        return False, "The task to update is not in this workspace."
    changed = []
    for field, limit in _TASK_FIELDS.items():
        if field in args and args[field] is not None:
            setattr(target, field, _clean_text(args[field], limit))
            changed.append(field)
    if not changed:
        return False, "Nothing to change."
    target.updated_at = utcnow()
    return True, "Updated " + ", ".join(changed)


def _exec_project_update(session: Session, workspace_id: str, task: Task, args: dict[str, Any]) -> tuple[bool, str]:
    project = session.get(Project, str(args.get("project_id") or ""))
    if project is None or project.workspace_id != workspace_id:
        return False, "The project to update is not in this workspace."
    changed = []
    for field, limit in _PROJECT_FIELDS.items():
        if field in args and args[field] is not None:
            setattr(project, field, _clean_text(args[field], limit))
            changed.append(field)
    if not changed:
        return False, "Nothing to change."
    project.updated_at = utcnow()
    return True, "Updated " + ", ".join(changed)


def register_executors() -> None:
    global _registered
    if _registered:
        return
    from daypilot_orchestrator.homepilot.action_mapping import register_executor
    register_executor("task.create", _exec_task_create)
    register_executor("task.update", _exec_task_update)
    register_executor("project.update", _exec_project_update)
    _registered = True


def connector_enabled() -> bool:
    return os.getenv("DAYPILOT_HOMEPILOT_CONNECTOR_ENABLED", "true").lower() not in ("0", "false", "no", "off")
