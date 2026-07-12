"""Private integration catalog + lifecycle API (batch I9/I10).

A curated (not public) catalog with tiers, manifest install, and certification.
Administrators install a manifest, DayPilot certifies it (conformance checks),
and only then can it be enabled — all without changing the core application.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from daypilot_orchestrator.integrations.certification import run_conformance
from daypilot_orchestrator.integrations.manifest import (
    get_entry,
    list_catalog,
    register_manifest,
    set_certified,
)
from daypilot_orchestrator.integrations.registry import build_provider, is_registered

router = APIRouter(prefix="/v1/catalog", tags=["integrations", "catalog"])


class InstallBody(BaseModel):
    manifest: dict[str, Any]
    tier: str = "experimental"


@router.get("")
def catalog(tier: str | None = None) -> dict[str, Any]:
    return {"catalog": list_catalog(tier)}


@router.post("/install", status_code=201)
def install(body: InstallBody) -> dict[str, Any]:
    try:
        entry = register_manifest(body.manifest, tier=body.tier, certified=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": entry["manifest"]["id"], "tier": entry["tier"], "certified": entry["certified"]}


@router.post("/{manifest_id}/certify")
def certify(manifest_id: str) -> dict[str, Any]:
    entry = get_entry(manifest_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="manifest not found")
    if not is_registered(manifest_id):
        raise HTTPException(status_code=409, detail="no provider registered to certify this manifest")
    report = run_conformance(entry["manifest"], build_provider(manifest_id))
    if report["passed"]:
        set_certified(manifest_id, True)
    return {"id": manifest_id, "certified": report["passed"], "report": report}
