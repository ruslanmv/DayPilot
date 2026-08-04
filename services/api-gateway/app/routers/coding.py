from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import CodingRun, Project
from daypilot_orchestrator.coding.interface import CoderSpec, CodingMode, CodingRunSpec
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


class CoderBody(BaseModel):
    """Which AI writes the patch, inside the chosen executor."""

    provider: str = ""
    model: str = ""


class CreateRunBody(BaseModel):
    task: str
    # Optional: a run on a project inherits that project's repository.
    repo: str = ""
    mode: str = "ask"
    branch: str | None = None
    baseBranch: str = "main"
    executor: str | None = None
    coder: CoderBody | None = None
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


def _repo_for(session: Session, body: CreateRunBody) -> str:
    """The repository this run works in: what was asked for, else the project's.

    A project that knows its repository does not make the caller retype it —
    which is what "add the repo to work" buys, once per project.
    """
    if body.repo.strip():
        return body.repo.strip()
    if body.projectId:
        project = session.get(Project, body.projectId)
        if project is not None and (project.repository or "").strip():
            return project.repository.strip()
    raise HTTPException(
        status_code=400,
        detail="this run needs a repository: pass repo, or set one on the project",
    )


@router.post("/runs", status_code=201)
def create_run(body: CreateRunBody, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        mode = CodingMode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{body.mode}'") from exc
    spec = CodingRunSpec(
        task=body.task,
        repo=_repo_for(session, body),
        mode=mode,
        branch=body.branch,
        base_branch=body.baseBranch,
        workspace_id=body.workspaceId,
        project_id=body.projectId,
        task_id=body.taskId,
        coder=CoderSpec(provider=body.coder.provider, model=body.coder.model)
        if body.coder
        else CoderSpec(),
    )
    adapter = resolve_adapter(body.executor, project_id=body.projectId)
    return create_coding_run(session, adapter, spec)


@router.get("/coders")
def list_coders(executor: str | None = None, projectId: str | None = None) -> dict[str, Any]:
    """Which AI coders the chosen executor can actually run.

    Asked of the executor rather than hard-coded, so the picker never offers a
    coder whose CLI or credential is missing on that host. An executor that
    cannot answer (older build, unreachable) reports none, and the run then uses
    that deployment's default.
    """
    adapter = resolve_adapter(executor, project_id=projectId)
    lookup = getattr(adapter, "available_coders", None)
    if lookup is None:
        return {"coders": [], "reachable": True, "detail": "this executor does not select coders"}
    try:
        return {"coders": lookup(), "reachable": True, "detail": ""}
    except httpx.HTTPError as exc:
        return {"coders": [], "reachable": False, "detail": f"executor unreachable: {exc}"}


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
