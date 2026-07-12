"""Persistent assistant chat-session API.

CRUD over conversations plus per-session message append/clear, backing the
ChatGPT/Claude-style history in the web shell. Storage only — the assistant's
routing and provider calls happen client-side against the other connected
endpoints; every turn is persisted here so it survives refresh and resume.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.chat import (
    append_message,
    clear_messages,
    create_session,
    delete_session,
    get_session_with_messages,
    list_sessions,
    rename_session,
)

from ..db import get_session

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class CreateBody(BaseModel):
    workspaceId: str = "default"
    title: str | None = None


class RenameBody(BaseModel):
    workspaceId: str = "default"
    title: str


class MessageBody(BaseModel):
    workspaceId: str = "default"
    role: str = "user"
    body: str = ""
    action: dict[str, Any] | None = None


@router.get("/sessions")
def sessions(workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    return list_sessions(session, workspaceId)


@router.post("/sessions", status_code=201)
def new_session(body: CreateBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    return create_session(session, body.workspaceId, body.title)


@router.get("/sessions/{session_id}")
def read_session(session_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return get_session_with_messages(session, workspaceId, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat session not found")


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, body: RenameBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return rename_session(session, body.workspaceId, session_id, body.title)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat session not found")


@router.delete("/sessions/{session_id}")
def remove_session(session_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return delete_session(session, workspaceId, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat session not found")


@router.delete("/sessions/{session_id}/messages")
def clear_session(session_id: str, workspaceId: str = "default", session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return clear_messages(session, workspaceId, session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat session not found")


@router.post("/sessions/{session_id}/messages", status_code=201)
def add_message(session_id: str, body: MessageBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return append_message(session, body.workspaceId, session_id, body.role, body.body, body.action)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat session not found")
