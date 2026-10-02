"""Read-only, expiring share links for dmind diagrams (batch B7).

Nothing is shared by default: the feature is off unless DAYPILOT_DMIND_SHARING=true, and each link is
an explicit act by an editor. A link points at one pinned revision, carries only a hash of its token,
shows what the viewer would see before it is created (redaction preview), can be revoked at once and
expires. Viewers can only read; unknown, expired and revoked links look identical (404).
"""

from __future__ import annotations

import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from daypilot_knowledge.db import AuditLog
from daypilot_knowledge.db.models import DiagramRevision, DiagramShare

from ..db import get_session
from .diagrams import access, owned

router = APIRouter(prefix="/v1/diagrams", tags=["diagrams"])
public = APIRouter(prefix="/v1/shared", tags=["diagrams"])

MAX_ACTIVE_PER_DIAGRAM = 20
MAX_HOURS = 24 * 90


def enabled() -> bool:
    return os.getenv("DAYPILOT_DMIND_SHARING", "false").lower() == "true"


def require_enabled() -> None:
    if not enabled():
        raise HTTPException(404, "sharing is not enabled; an administrator can turn it on")


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def audit(session: Session, event: str, share: DiagramShare, actor: str | None = None) -> None:
    session.add(
        AuditLog(
            event_type=f"diagram.share.{event}",
            risk="medium" if event == "created" else "low",
            decision="recorded",
            payload_json={
                "workspaceId": share.workspace_id,
                "diagramId": share.diagram_id,
                "shareId": share.id,
                "revision": share.revision,
                "actor": actor,
            },
        )
    )


def redact(document: dict[str, Any], include_notes: bool) -> dict[str, Any]:
    """Exactly what a viewer receives: structure and labels; metadata is never included."""
    nodes = []
    for n in document.get("nodes", []):
        item = {"id": n["id"], "label": n["label"]}
        if include_notes and n.get("notes"):
            item["notes"] = n["notes"]
        if "collapsed" in n:
            item["collapsed"] = n["collapsed"]
        if "position" in n:
            item["position"] = n["position"]
        nodes.append(item)
    edges = [
        {k: e[k] for k in ("id", "source", "target", "kind", "label") if k in e}
        for e in document.get("edges", [])
    ]
    return {
        "schema_version": document["schema_version"],
        "id": document["id"],
        "title": document["title"],
        "kind": document["kind"],
        "nodes": nodes,
        "edges": edges,
    }


class ShareIn(BaseModel):
    expiresInHours: int = Field(168, ge=1, le=MAX_HOURS)
    includeNotes: bool = False


def describe(row: DiagramShare) -> dict[str, Any]:
    expires = aware(row.expires_at)
    state = "revoked" if row.revoked_at else "expired" if expires <= now() else "active"
    return {
        "id": row.id,
        "diagramId": row.diagram_id,
        "revision": row.revision,
        "includeNotes": row.include_notes,
        "createdBy": row.created_by,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "expiresAt": expires.isoformat(),
        "revokedAt": row.revoked_at.isoformat() if row.revoked_at else None,
        "views": row.views,
        "lastViewedAt": row.last_viewed_at.isoformat() if row.last_viewed_at else None,
        "state": state,
    }


def head_document(session: Session, diagram_id: str, revision: int) -> dict[str, Any]:
    rev = session.get(DiagramRevision, (diagram_id, revision))
    if rev is None:
        raise HTTPException(404, "revision not found")
    return rev.document_json


@router.get("/{diagram_id}/shares/preview")
def preview(
    diagram_id: str,
    include_notes: bool = Query(False, alias="includeNotes"),
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """What a viewer would receive for the current revision, before any link exists."""
    require_enabled()
    row = owned(session, diagram_id, workspace)
    return {"revision": row.revision, "document": redact(row.document_json, include_notes)}


@router.post("/{diagram_id}/shares", status_code=201)
def create_share(
    diagram_id: str,
    body: ShareIn,
    request: Request,
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_enabled()
    row = owned(session, diagram_id, workspace)
    if row.archived:
        raise HTTPException(409, "restore the diagram before sharing it")
    active = session.execute(
        select(func.count())
        .select_from(DiagramShare)
        .where(
            DiagramShare.diagram_id == diagram_id,
            DiagramShare.revoked_at.is_(None),
            DiagramShare.expires_at > now(),
        )
    ).scalar_one()
    if active >= MAX_ACTIVE_PER_DIAGRAM:
        raise HTTPException(409, f"at most {MAX_ACTIVE_PER_DIAGRAM} active links per diagram; revoke one first")
    token = secrets.token_urlsafe(32)
    share = DiagramShare(
        diagram_id=diagram_id,
        workspace_id=workspace,
        token_hash=token_hash(token),
        revision=row.revision,
        include_notes=body.includeNotes,
        created_by=request.headers.get("x-user-id"),
        created_at=now(),
        expires_at=now() + timedelta(hours=body.expiresInHours),
        views=0,
    )
    session.add(share)
    session.flush()
    audit(session, "created", share, share.created_by)
    # The token is shown once; only its hash is kept.
    return {**describe(share), "token": token, "path": f"/v1/shared/{token}/view"}


@router.get("/{diagram_id}/shares")
def list_shares(
    diagram_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    require_enabled()
    owned(session, diagram_id, workspace)
    rows = session.execute(
        select(DiagramShare)
        .where(DiagramShare.diagram_id == diagram_id, DiagramShare.workspace_id == workspace)
        .order_by(DiagramShare.created_at.desc())
        .limit(100)
    ).scalars()
    return {"items": [describe(r) for r in rows]}


@router.delete("/{diagram_id}/shares/{share_id}")
def revoke_share(
    diagram_id: str,
    share_id: str,
    request: Request,
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    require_enabled()
    owned(session, diagram_id, workspace)
    share = session.get(DiagramShare, share_id)
    if share is None or share.diagram_id != diagram_id or share.workspace_id != workspace:
        raise HTTPException(404, "share not found")
    if share.revoked_at is None:
        session.execute(
            update(DiagramShare).where(DiagramShare.id == share_id).values(revoked_at=now())
        )
        session.refresh(share)
        audit(session, "revoked", share, request.headers.get("x-user-id"))
    return describe(share)


def lookup(session: Session, token: str) -> DiagramShare:
    """One uniform 404 for unknown, expired and revoked links, so nothing can be probed."""
    require_enabled()
    share = session.execute(
        select(DiagramShare).where(DiagramShare.token_hash == token_hash(token))
    ).scalar_one_or_none()
    if share is None or share.revoked_at is not None or aware(share.expires_at) <= now():
        raise HTTPException(404, "this link is not available")
    return share


def record_view(session: Session, share: DiagramShare) -> None:
    session.execute(
        update(DiagramShare)
        .where(DiagramShare.id == share.id)
        .values(views=DiagramShare.views + 1, last_viewed_at=now())
    )
    audit(session, "viewed", share)


SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


@public.get("/{token}")
def shared_json(token: str, session: Session = Depends(get_session)) -> JSONResponse:
    share = lookup(session, token)
    document = redact(head_document(session, share.diagram_id, share.revision), share.include_notes)
    record_view(session, share)
    return JSONResponse({"readOnly": True, "revision": share.revision, "document": document}, headers=SAFE_HEADERS)


def outline(document: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Depth-first (iterative, so a deep chain cannot exhaust the stack) by branch/flow links."""
    kind = "flow" if document["kind"] == "flowchart" else "branch"
    nodes = {n["id"]: n for n in document["nodes"]}
    children: dict[str, list[str]] = {}
    has_parent: set[str] = set()
    for e in document["edges"]:
        if e["kind"] == kind and e["source"] in nodes and e["target"] in nodes:
            children.setdefault(e["source"], []).append(e["target"])
            has_parent.add(e["target"])
    order: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    stack = [(0, n["id"]) for n in reversed(document["nodes"]) if n["id"] not in has_parent]
    while stack:
        depth, nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        order.append((depth, nodes[nid]))
        stack.extend((depth + 1, c) for c in reversed(children.get(nid, [])))
    order.extend((0, n) for n in document["nodes"] if n["id"] not in seen)
    return order


@public.get("/{token}/view")
def shared_view(token: str, session: Session = Depends(get_session)) -> HTMLResponse:
    share = lookup(session, token)
    document = redact(head_document(session, share.diagram_id, share.revision), share.include_notes)
    record_view(session, share)
    rows = []
    for depth, n in outline(document):
        note = f'<p class="n">{html.escape(n["notes"])}</p>' if n.get("notes") else ""
        pad = min(depth, 30) * 18
        rows.append(f'<li style="margin-left:{pad}px"><span>{html.escape(n["label"])}</span>{note}</li>')
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        f"<title>{html.escape(document['title'])}</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:50rem;margin:2rem auto;padding:0 1rem}"
        "ul{list-style:none;padding:0}li{padding:.15rem 0}.n{margin:.1rem 0 .4rem;color:#555;white-space:pre-wrap}"
        ".b{color:#555;font-size:.9rem}</style></head><body>"
        f"<h1>{html.escape(document['title'])}</h1>"
        f'<p class="b">Read-only snapshot, revision {share.revision}.</p>'
        f"<ul>{''.join(rows)}</ul></body></html>"
    )
    headers = {
        **SAFE_HEADERS,
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    }
    return HTMLResponse(page, headers=headers)
