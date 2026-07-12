from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval
from daypilot_orchestrator.approvals.center import (
    ApprovalDecisionError,
    decide,
    export_audit,
    required_role,
    summary,
)

from .. import repository
from ..auth import Principal, get_principal
from ..db import get_session
from ..rbac import ROLE_RANK, require_operator

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


class DecisionBody(BaseModel):
    decision: str
    reason: str | None = None


@router.get("")
def list_approvals(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    status: str | None = None,
    risk: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return repository.list_approvals(
        session, workspace_id=workspaceId, status=status, risk=risk,
        sort=sort, order=order, cursor=cursor, limit=limit,
    )


@router.get("/summary")
def approvals_summary(session: Session = Depends(get_session), workspaceId: str = "default") -> dict[str, Any]:
    return summary(session, workspaceId)


@router.post("/{approval_id}/decide")
def decide_approval(
    approval_id: str,
    body: DecisionBody,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    """Approve/reject an item. RBAC: the role required depends on the resource."""
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    needed = required_role(approval.resource_type)
    if ROLE_RANK.get(principal.role, -1) < ROLE_RANK.get(needed, 99):
        raise HTTPException(
            status_code=403,
            detail=f"Deciding a '{approval.resource_type}' approval requires role '{needed}'.",
        )
    try:
        return decide(session, approval_id, body.decision, principal.subject, body.reason)
    except ApprovalDecisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/audit/export")
def audit_export(
    session: Session = Depends(get_session),
    fmt: str = "jsonl",
    _principal: Principal = Depends(require_operator),
):
    from starlette.responses import Response

    content, media_type = export_audit(session, fmt)
    return Response(content, media_type=media_type)
