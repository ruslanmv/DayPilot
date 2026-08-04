from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.design.bundle_intake import apply_review, intake_bundle
from daypilot_orchestrator.design.matrix_designer_adapter import (
    DesignerError,
    matrix_designer_from_env,
)

from ..db import get_session

router = APIRouter(prefix="/v1/design", tags=["design"])


class BlueprintsRequest(BaseModel):
    idea: str
    references: list[dict[str, str]] | None = None
    constraints: dict[str, Any] | None = None


class RefineRequest(BaseModel):
    idea: str
    message: str = ""
    candidateId: str = "standard"
    constraints: dict[str, Any] | None = None


class BundleRequest(BaseModel):
    idea: str
    blueprint: str = ""
    candidateId: str = ""
    # Where the batches get built. Optional: a project can be designed first and
    # pointed at a repository later, before the first batch runs.
    repository: str = ""
    workspaceId: str = "default"
    projectId: str | None = None
    intake: bool = True


class ReviewRequest(BaseModel):
    """Review a bundle you already have, or design one from an idea and review that."""

    bundle: dict[str, Any] | None = None
    idea: str = ""
    candidateId: str = ""
    target: str = ""
    kind: str = "design-bundle"
    workspaceId: str = "default"
    projectId: str | None = None


def _serialize_batch(batch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "title": batch.title,
        "description": batch.description,
        "dependsOn": batch.depends_on,
        "acceptance": batch.acceptance,
        "estimateHours": batch.estimate_hours,
        "allowedFiles": batch.allowed_files,
        "mustNotChange": batch.must_not_change,
    }


def _serialize_bundle(bundle) -> dict[str, Any]:
    return {
        "bundleId": bundle.bundle_id,
        "title": bundle.title,
        "framework": bundle.framework,
        "visualTarget": bundle.visual_target,
        "architecture": bundle.architecture,
        "acceptanceCriteria": bundle.acceptance_criteria,
        "validationStatus": bundle.validation_status,
        "batches": [_serialize_batch(b) for b in bundle.batches],
    }


def _serialize_proposal(proposal) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "id": c.id,
                "tier": c.tier,
                "title": c.title,
                "summary": c.summary,
                "difficulty": c.difficulty,
                "estimate": c.estimate,
                "fileCount": c.file_count,
                "stack": c.stack,
                "recommended": c.recommended,
                "batches": [_serialize_batch(b) for b in c.batches],
            }
            for c in proposal.candidates
        ],
        "recommendedId": proposal.recommended.id if proposal.recommended else "",
        "matrixRules": proposal.matrix_rules,
        "violations": proposal.violations,
        "reply": proposal.reply,
    }


def _designer():
    """The adapter, with upstream failures turned into honest gateway errors.

    A design step that cannot reach the designer must say so — never return an
    empty plan that looks like a real one.
    """
    return matrix_designer_from_env()


def _guard(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except DesignerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"matrix designer unavailable: {exc}") from exc


@router.post("/blueprints")
def blueprints(body: BlueprintsRequest) -> dict[str, Any]:
    """Propose the plans to choose between — the first step of a build from an idea."""
    proposal = _guard(_designer().generate_blueprints, body.idea, body.references, body.constraints)
    return _serialize_proposal(proposal)


@router.post("/refine")
def refine(body: RefineRequest) -> dict[str, Any]:
    """Adjust a candidate plan from free text before committing to it."""
    proposal = _guard(
        _designer().refine_design, body.idea, body.message, body.candidateId, body.constraints
    )
    return _serialize_proposal(proposal)


@router.post("/bundles", status_code=201)
def create_bundle(body: BundleRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Design the chosen plan in full and (optionally) intake the bundle as work."""
    bundle = _guard(_designer().submit_bundle, body.idea, body.blueprint, body.candidateId)
    result: dict[str, Any] = {"bundle": _serialize_bundle(bundle)}
    if body.intake:
        result["intake"] = intake_bundle(
            session, body.workspaceId, bundle, body.projectId, body.repository
        )
    return result


@router.post("/review", status_code=201)
def review(body: ReviewRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Govern a design before it is built; findings land on the project."""
    designer = _designer()
    document = body.bundle
    if not document:
        if not body.idea.strip():
            raise HTTPException(status_code=400, detail="a review needs a bundle or an idea")
        document = _guard(designer.submit_bundle, body.idea, "", body.candidateId).document
    result = _guard(designer.review_bundle, document, body.target, body.kind)
    return apply_review(session, body.workspaceId, result, body.projectId)
