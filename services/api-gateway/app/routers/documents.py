from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Project
from daypilot_knowledge.document_ai import chat, compute_project_status, generate_output
from daypilot_knowledge.ingest import SourceNotPermitted, ingest_document
from daypilot_knowledge.sources import get_registry

from .. import repository
from ..db import get_session

router = APIRouter(prefix="/v1/documents", tags=["documents"])


class IngestBody(BaseModel):
    path: str
    content: str | None = None
    title: str | None = None
    projectId: str | None = None
    sourceKind: str = "Local PC"


class ChatBody(BaseModel):
    query: str
    projectId: str | None = None
    documentId: str | None = None
    limit: int = 5


class GenerateBody(BaseModel):
    title: str
    content: str
    kind: str = "summary"


class GrantBody(BaseModel):
    kind: str = "local"
    scope: str
    permission: str = "read_index"


@router.get("")
def list_documents(
    session: Session = Depends(get_session),
    projectId: str | None = None,
    status: str | None = None,
    source: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return repository.list_documents(
        session, project_id=projectId, status=status, source=source,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


@router.get("/sources")
def sources() -> dict[str, Any]:
    return {
        "grants": [
            {"kind": g.kind, "scope": g.scope, "permission": g.permission}
            for g in get_registry().grants()
        ]
    }


@router.post("/sources/grant", status_code=201)
def grant_source(body: GrantBody) -> dict[str, Any]:
    g = get_registry().grant(body.kind, body.scope, body.permission)
    return {"kind": g.kind, "scope": g.scope, "permission": g.permission}


@router.post("/ingest", status_code=201)
def ingest(body: IngestBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return ingest_document(
            session, body.path, content=body.content, title=body.title,
            project_id=body.projectId, source_kind=body.sourceKind,
        )
    except SourceNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/chat")
def document_chat(body: ChatBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return chat(session, body.query, project_id=body.projectId, document_id=body.documentId, limit=body.limit)


@router.post("/{document_id}/generate", status_code=201)
def generate(document_id: str, body: GenerateBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return generate_output(session, document_id, body.title, body.content, body.kind)
    except KeyError:
        raise HTTPException(status_code=404, detail="Source document not found") from None


@router.get("/project-status/{project_id}")
def project_status(project_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return compute_project_status(session, project)
