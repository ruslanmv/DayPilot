from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import CodingRun
from daypilot_orchestrator.coding.interface import CodingMode, CodingRunSpec
from daypilot_orchestrator.coding.provider_routing import available_executors, resolve_adapter
from daypilot_orchestrator.coding.service import (
    WriteNotApproved,
    create_coding_run,
    get_coding_run,
    perform_write,
    review_coding_run,
)

from ..db import get_session
from ..pagination import keyset_page, page_response

router = APIRouter(prefix="/v1/coding", tags=["coding"])


class CreateRunBody(BaseModel):
    task: str
    repo: str
    mode: str = "ask"
    branch: str | None = None
    baseBranch: str = "main"
    executor: str | None = None
    workspaceId: str = "default"
    projectId: str | None = None
    taskId: str | None = None


class ReviewBody(BaseModel):
    decision: str
    reason: str | None = None


def _serialize_run(run: CodingRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "workspaceId": run.workspace_id,
        "executor": run.executor,
        "repo": run.repo,
        "branch": run.branch,
        "prUrl": run.pr_url,
        "mode": run.mode,
        "status": run.status,
        "filesChanged": run.files_changed,
        "testsPassed": run.tests_passed,
        "testsTotal": run.tests_total,
        "risk": run.risk,
        "riskScore": run.risk_score,
        "diffSummary": run.diff_summary,
        "projectId": run.project_id,
        "taskId": run.task_id,
    }


@router.get("/executors")
def list_executors() -> dict[str, Any]:
    """Available coding executors with capabilities and enabled state."""
    return {"executors": available_executors()}


@router.get("/runs")
def list_runs(
    session: Session = Depends(get_session),
    workspaceId: str = "default",
    status: str | None = None,
    executor: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = select(CodingRun).where(CodingRun.workspace_id == workspaceId)
    if status:
        stmt = stmt.where(CodingRun.status == status)
    if executor:
        stmt = stmt.where(CodingRun.executor == executor)
    rows, next_cursor = keyset_page(
        session, stmt, model=CodingRun, sort_field="updated_at", order="desc",
        cursor=cursor, limit=limit, allowed_sort_fields=("created_at", "updated_at"),
    )
    return page_response([_serialize_run(r) for r in rows], next_cursor, limit)


@router.post("/runs", status_code=201)
def create_run(body: CreateRunBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        mode = CodingMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{body.mode}'") from exc
    spec = CodingRunSpec(
        task=body.task,
        repo=body.repo,
        mode=mode,
        branch=body.branch,
        base_branch=body.baseBranch,
        workspace_id=body.workspaceId,
        project_id=body.projectId,
        task_id=body.taskId,
    )
    adapter = resolve_adapter(body.executor, project_id=body.projectId)
    return create_coding_run(session, adapter, spec)


@router.get("/runs/{run_id}")
def read_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    run = get_coding_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Coding run not found")
    return run


@router.post("/runs/{run_id}/review")
def review_run(run_id: str, body: ReviewBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return review_coding_run(session, run_id, body.decision, body.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="Coding run not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/write")
def write_run(run_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Perform the repository write. Refused (403) without an approved approval."""
    try:
        return perform_write(session, run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Coding run not found") from None
    except WriteNotApproved as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
