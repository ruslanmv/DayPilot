"""Isolated dmind API: workspace authorization, CAS saves and immutable revisions.

Generation and coding handoff never intake tasks or execute code. Sharing is via
explicit portable exports in the UI; this router creates no anonymous public URLs.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session, defer

from daypilot_knowledge.db.models import Diagram, DiagramRevision, Project, WorkspaceMembership
from daypilot_orchestrator.design.dmind_contract import validate_diagram
from daypilot_orchestrator.design.matrix_designer_adapter import (
    DesignerError,
    matrix_designer_from_env,
)

from .. import identity
from ..auth import get_principal
from ..db import get_session
from ..pagination import keyset_page, page_response
from ..rbac import ROLE_RANK

router = APIRouter(prefix="/v1/diagrams", tags=["diagrams"])


def access(request: Request, session: Session = Depends(get_session)) -> str:
    workspace = request.headers.get("x-workspace-id", "default")
    if len(workspace) > 36 or not workspace.strip():
        raise HTTPException(400, "invalid workspace")
    resolved = identity.resolve_session(session, request.cookies.get(identity.COOKIE_NAME))
    if resolved:
        user, auth_session = resolved
        member = session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.workspace_id == workspace,
            )
        ).scalar_one_or_none()
        if not member:
            raise HTTPException(403, "workspace membership required")
        role = member.role
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-csrf-token") != auth_session.csrf_token:
                raise HTTPException(403, "csrf_failed")
    else:
        if os.getenv("DAYPILOT_REQUIRE_SESSION", "false").lower() == "true":
            raise HTTPException(401, "session required")
        principal = get_principal(request.headers.get("authorization"))
        # Token roles are tied to the principal's workspace. Single-user local
        # mode may choose workspaces; authenticated mode never trusts the header.
        if (
            os.getenv("DAYPILOT_AUTH_ENABLED", "false").lower() == "true"
            and workspace != principal.workspace_id
        ):
            raise HTTPException(403, "workspace membership required")
        role = principal.role
    minimum = 0 if request.method == "GET" else 2
    if ROLE_RANK.get(role, -1) < minimum:
        raise HTTPException(403, "diagram access denied for this role")
    return workspace


class SaveIn(BaseModel):
    document: dict[str, Any]
    expectedRevision: int = Field(0, ge=0)
    # Omitted keeps the stored state: an ordinary save must never silently unarchive.
    archived: bool | None = None


class GenerateIn(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    content: str = Field("", max_length=100000)
    kind: str = "mindmap"
    candidateId: str = "standard"
    useDesigner: bool = False


class HandoffIn(BaseModel):
    document: dict[str, Any]
    candidateId: str = "standard"


def checked(document):
    try:
        return validate_diagram(document)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def reason(response: httpx.Response) -> str:
    """The designer's own explanation (plain text, bounded), e.g. a provider-policy refusal."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail[:300] if isinstance(detail, str) else ""


MAX_TAGS = 20
MAX_TAG_LENGTH = 40


def index_fields(document: dict[str, Any]) -> tuple[str | None, str | None]:
    """Validate and normalise ``metadata.tags`` / ``metadata.project_id`` in place.

    Returns ``(project_id, tags_text)`` for the filter columns. Tags are lower-cased, de-duplicated
    and stored as ``|a|b|`` so a single portable LIKE finds one. The document stays the source of
    truth: the columns are derived from it on every save.
    """
    meta = document.get("metadata")
    if not isinstance(meta, dict):
        return None, None
    tags = meta.get("tags")
    tags_text = None
    if tags is not None:
        if not isinstance(tags, list) or len(tags) > MAX_TAGS:
            raise HTTPException(422, f"tags must be a list of at most {MAX_TAGS} items")
        clean: list[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                raise HTTPException(422, "each tag must be text")
            value = " ".join(tag.split()).lower()
            if not value or len(value) > MAX_TAG_LENGTH or "|" in value or not value.isprintable():
                raise HTTPException(422, f"tags must be 1-{MAX_TAG_LENGTH} printable characters without '|'")
            if value not in clean:
                clean.append(value)
        meta["tags"] = clean
        tags_text = "|" + "|".join(clean) + "|" if clean else None
    project = meta.get("project_id")
    if project is not None and (not isinstance(project, str) or not 0 < len(project) <= 36):
        raise HTTPException(422, "project_id must be a project id")
    return project, tags_text


def known_project(session: Session, workspace: str, project_id: str | None) -> bool:
    if project_id is None:
        return True
    row = session.get(Project, project_id)
    return row is not None and row.workspace_id == workspace


def upstream(path: str, payload: dict[str, Any]):
    try:
        return matrix_designer_from_env()._post(path, payload)
    except DesignerError as exc:
        raise HTTPException(400, str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (400, 422):
            why = reason(exc.response)
            raise HTTPException(
                422,
                f"Matrix Designer rejected the request: {why}"
                if why
                else "Matrix Designer rejected the diagram or source",
            ) from exc
        if status == 404:
            raise HTTPException(
                502, "Install the Matrix Designer dmind interoperability update"
            ) from exc
        if status in (401, 403):
            raise HTTPException(
                502, "Matrix Designer refused the configured API key (MATRIX_DESIGNER_API_KEY)"
            ) from exc
        raise HTTPException(502, "Matrix Designer request failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Matrix Designer is unavailable; use local outline mode") from exc


def snapshot(row: Diagram) -> dict[str, Any]:
    return {
        "id": row.id,
        "revision": row.revision,
        "archived": row.archived,
        "document": row.document_json,
    }


@router.post("/generate")
def generate(body: GenerateIn, workspace: str = Depends(access)) -> dict[str, Any]:
    result = upstream(
        "/design/diagrams",
        {
            "topic": body.topic,
            "content": body.content,
            "kind": body.kind,
            "candidate_id": body.candidateId,
            "use_designer": body.useDesigner,
        },
    )
    result["diagram"] = checked(result.get("diagram"))
    return result


@router.post("/design-bundle")
def design_bundle(body: HandoffIn, workspace: str = Depends(access)) -> dict[str, Any]:
    return upstream(
        "/design/diagrams/bundle",
        {"diagram": checked(body.document), "candidate_id": body.candidateId},
    )


def like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def summary(row: Diagram) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "revision": row.revision,
        "archived": row.archived,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        "tags": [t for t in (row.tags_text or "").split("|") if t],
        "projectId": row.project_id,
    }


@router.get("")
def listing(
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
    limit: int = Query(200, ge=1, le=200),
    cursor: str | None = None,
    q: str | None = Query(None, max_length=200),
    tag: str | None = Query(None, max_length=MAX_TAG_LENGTH),
    project_id: str | None = Query(None, max_length=36),
    archived: str = Query("include", pattern="^(include|exclude|only)$"),
    sort: str = Query("updated_at", pattern="^(updated_at|created_at)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    """Newest first, cursor-paged. Defaults match the original behaviour (200, archived included)."""
    stmt = (
        select(Diagram)
        .options(defer(Diagram.document_json))
        .where(Diagram.workspace_id == workspace)
    )
    if q and q.strip():
        stmt = stmt.where(Diagram.title.ilike(f"%{like_escape(q.strip())}%", escape="\\"))
    if tag and tag.strip():
        needle = like_escape(" ".join(tag.split()).lower())
        stmt = stmt.where(Diagram.tags_text.like(f"%|{needle}|%", escape="\\"))
    if project_id:
        stmt = stmt.where(Diagram.project_id == project_id)
    if archived == "exclude":
        stmt = stmt.where(Diagram.archived.is_(False))
    elif archived == "only":
        stmt = stmt.where(Diagram.archived.is_(True))
    rows, next_cursor = keyset_page(
        session,
        stmt,
        model=Diagram,
        sort_field=sort,
        order=order,
        cursor=cursor,
        limit=limit,
        allowed_sort_fields=("updated_at", "created_at"),
    )
    return page_response([summary(r) for r in rows], next_cursor, limit)


@router.post("", status_code=201)
def create(
    body: SaveIn, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    document = checked(body.document)
    document["id"] = str(uuid.uuid4())  # Import is always a copy, never an overwrite.
    project, tags_text = index_fields(document)
    if not known_project(session, workspace, project):
        # A copy never inherits a project from another workspace.
        document["metadata"].pop("project_id", None)
        project = None
    row = Diagram(
        id=document["id"],
        workspace_id=workspace,
        title=document["title"],
        document_json=document,
        revision=1,
        archived=False,
        project_id=project,
        tags_text=tags_text,
    )
    session.add(row)
    session.flush()
    session.add(DiagramRevision(diagram_id=row.id, revision=1, document_json=document))
    return snapshot(row)


def owned(session: Session, diagram_id: str, workspace: str) -> Diagram:
    row = session.get(Diagram, diagram_id)
    if row is None or row.workspace_id != workspace:
        raise HTTPException(404, "diagram not found")
    return row


@router.get("/{diagram_id}")
def load(
    diagram_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    return snapshot(owned(session, diagram_id, workspace))


def revision_summary(row: DiagramRevision, with_document: bool) -> dict[str, Any]:
    doc = row.document_json or {}
    out: dict[str, Any] = {
        "revision": row.revision,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "title": doc.get("title"),
        "nodes": len(doc.get("nodes", [])),
        "edges": len(doc.get("edges", [])),
    }
    if with_document:
        out["document"] = doc
    return out


@router.get("/{diagram_id}/revisions")
def revisions(
    diagram_id: str,
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
    limit: int = Query(100, ge=1, le=100),
    before: int | None = Query(None, ge=1),
    summary_only: bool = Query(False, alias="summary"),
) -> dict[str, Any]:
    """Newest first. ``before`` pages to older snapshots; every snapshot stays stored."""
    owned(session, diagram_id, workspace)
    stmt = select(DiagramRevision).where(DiagramRevision.diagram_id == diagram_id)
    if before is not None:
        stmt = stmt.where(DiagramRevision.revision < before)
    rows = list(
        session.execute(stmt.order_by(DiagramRevision.revision.desc()).limit(limit + 1)).scalars()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "items": [revision_summary(r, not summary_only) for r in rows],
        "hasMore": more,
        "nextBefore": rows[-1].revision if more and rows else None,
    }


@router.get("/{diagram_id}/revisions/{revision}")
def one_revision(
    diagram_id: str,
    revision: int,
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    owned(session, diagram_id, workspace)
    row = session.get(DiagramRevision, (diagram_id, revision))
    if row is None:
        raise HTTPException(404, "revision not found")
    return revision_summary(row, True)


@router.put("/{diagram_id}")
def save(
    diagram_id: str,
    body: SaveIn,
    workspace: str = Depends(access),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    owned(session, diagram_id, workspace)
    document = checked(body.document)
    document["id"] = diagram_id
    project, tags_text = index_fields(document)
    if not known_project(session, workspace, project):
        raise HTTPException(422, "unknown project: choose a project in this workspace")
    revision = body.expectedRevision + 1
    # A single compare-and-swap update prevents silent multi-tab overwrites.
    result = session.execute(
        update(Diagram)
        .where(
            Diagram.id == diagram_id,
            Diagram.workspace_id == workspace,
            Diagram.revision == body.expectedRevision,
        )
        .values(
            document_json=document,
            title=document["title"],
            revision=revision,
            project_id=project,
            tags_text=tags_text,
            **({} if body.archived is None else {"archived": body.archived}),
        )
    )
    if result.rowcount != 1:
        raise HTTPException(409, "diagram changed elsewhere; reload or save a copy")
    session.add(DiagramRevision(diagram_id=diagram_id, revision=revision, document_json=document))
    session.flush()
    session.expire_all()
    return snapshot(owned(session, diagram_id, workspace))
