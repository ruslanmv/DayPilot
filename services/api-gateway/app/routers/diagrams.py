"""Isolated dmind API: workspace authorization, CAS saves and immutable revisions.

Generation and coding handoff never intake tasks or execute code. Sharing is via
explicit portable exports in the UI; this router creates no anonymous public URLs.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from daypilot_knowledge.db.models import Diagram, DiagramRevision, WorkspaceMembership
from daypilot_orchestrator.design.dmind_contract import validate_diagram
from daypilot_orchestrator.design.matrix_designer_adapter import (
    DesignerError,
    matrix_designer_from_env,
)

from .. import identity
from ..auth import get_principal
from ..db import get_session
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


@router.get("")
def listing(
    workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    rows = session.execute(
        select(Diagram)
        .where(Diagram.workspace_id == workspace)
        .order_by(Diagram.updated_at.desc())
        .limit(200)
    ).scalars()
    return {
        "items": [
            {"id": r.id, "title": r.title, "revision": r.revision, "archived": r.archived}
            for r in rows
        ]
    }


@router.post("", status_code=201)
def create(
    body: SaveIn, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    document = checked(body.document)
    document["id"] = str(uuid.uuid4())  # Import is always a copy, never an overwrite.
    row = Diagram(
        id=document["id"],
        workspace_id=workspace,
        title=document["title"],
        document_json=document,
        revision=1,
        archived=False,
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


@router.get("/{diagram_id}/revisions")
def revisions(
    diagram_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    owned(session, diagram_id, workspace)
    rows = session.execute(
        select(DiagramRevision)
        .where(DiagramRevision.diagram_id == diagram_id)
        .order_by(DiagramRevision.revision.desc())
        .limit(100)
    ).scalars()
    return {"items": [{"revision": r.revision, "document": r.document_json} for r in rows]}


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
            **({} if body.archived is None else {"archived": body.archived}),
        )
    )
    if result.rowcount != 1:
        raise HTTPException(409, "diagram changed elsewhere; reload or save a copy")
    session.add(DiagramRevision(diagram_id=diagram_id, revision=revision, document_json=document))
    session.flush()
    session.expire_all()
    return snapshot(owned(session, diagram_id, workspace))
