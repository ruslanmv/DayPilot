from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from daypilot_orchestrator.design.bundle_intake import apply_review, intake_bundle
from daypilot_orchestrator.design.matrix_designer_adapter import matrix_designer_from_env

from ..db import get_session

router = APIRouter(prefix="/v1/design", tags=["design"])


class BundleRequest(BaseModel):
    idea: str
    blueprint: str = ""
    workspaceId: str = "default"
    projectId: str | None = None
    intake: bool = True


class ReviewRequest(BaseModel):
    target: str
    kind: str = "ui"
    context: str = ""
    workspaceId: str = "default"
    projectId: str | None = None


def _serialize_bundle(bundle) -> dict[str, Any]:
    return {
        "bundleId": bundle.bundle_id,
        "title": bundle.title,
        "framework": bundle.framework,
        "visualTarget": bundle.visual_target,
        "architecture": bundle.architecture,
        "acceptanceCriteria": bundle.acceptance_criteria,
        "batches": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "dependsOn": b.depends_on,
                "acceptance": b.acceptance,
                "estimateHours": b.estimate_hours,
            }
            for b in bundle.batches
        ],
    }


@router.post("/bundles", status_code=201)
def create_bundle(body: BundleRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Submit an idea to Matrix Designer and (optionally) intake the bundle as work."""
    adapter = matrix_designer_from_env()
    bundle = adapter.submit_bundle(body.idea, body.blueprint)
    result: dict[str, Any] = {"bundle": _serialize_bundle(bundle)}
    if body.intake:
        result["intake"] = intake_bundle(session, body.workspaceId, bundle, body.projectId)
    return result


@router.post("/review", status_code=201)
def review(body: ReviewRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Ask Matrix Designer to review an artifact; attach findings to the project."""
    adapter = matrix_designer_from_env()
    result = adapter.review_artifact(body.target, body.kind, body.context)
    return apply_review(session, body.workspaceId, result, body.projectId)
