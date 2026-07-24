from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import knowledge_sources as ks
from ..db import get_session

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])


class AddLocalBody(BaseModel):
    path: str
    displayName: str | None = None
    workspaceId: str = "default"


class WsBody(BaseModel):
    workspaceId: str = "default"


@router.get("/sources")
def list_sources(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return ks.list_sources(session, workspaceId)


@router.post("/sources/local", status_code=201)
def add_local(body: AddLocalBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    out = ks.add_local(session, body.workspaceId, body.path, body.displayName)
    if "error" in out:
        raise HTTPException(status_code=422 if out["error"] != "path_not_found" else 404, detail=out.get("detail", out["error"]))
    return out


@router.post("/sources/{source_id}/reindex")
def reindex(source_id: str, body: WsBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    out = ks.reindex(session, body.workspaceId, source_id)
    if "error" in out:
        raise HTTPException(status_code=404, detail="source_not_found")
    return out


@router.get("/sources/{source_id}/jobs")
def source_jobs(source_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return ks.source_jobs(session, workspaceId, source_id)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> None:
    if not ks.delete_source(session, workspaceId, source_id):
        raise HTTPException(status_code=404, detail="source_not_found")


@router.post("/box/oauth/start")
def box_oauth_start(body: WsBody) -> dict[str, Any]:
    return ks.box_oauth_start(body.workspaceId)
