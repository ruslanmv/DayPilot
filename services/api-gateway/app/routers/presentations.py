"""Presentations: company brand kits, decks with immutable revisions, actual-file review, weekly series.

Off unless DAYPILOT_PRESENTATIONS=true (only /capabilities answers when off). Workspace membership
and roles come from the same checks as diagrams; every lookup is scoped to the caller's workspace,
and ids from the browser are references, never authority.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daypilot_knowledge.db.models import (
    PresentationArtifact,
    PresentationAsset,
    PresentationBrandKit,
    PresentationCompany,
    PresentationDeck,
    PresentationOccurrence,
    PresentationRevision,
    PresentationRun,
    PresentationSeries,
)

from ..db import get_session
from ..presentations import brandkit, engine, genres, images, render, store, weekly, worker
from ..rbac import ROLE_RANK
from .diagrams import access, access_role

router = APIRouter(prefix="/v1/presentations", tags=["presentations"])


def enabled() -> bool:
    return os.getenv("DAYPILOT_PRESENTATIONS", "false").lower() == "true"


def on() -> None:
    if not enabled():
        raise HTTPException(404, "Presentations are not enabled. An administrator can set DAYPILOT_PRESENTATIONS=true.")


def problem(exc: engine.EngineError) -> HTTPException:
    if exc.internal:
        return HTTPException(503, str(exc))
    return HTTPException(422, {"message": str(exc), "problems": exc.problems[:20]})


# ----------------------------------------------------------------------------- lookups (scoped)


def company(session: Session, workspace: str, company_id: str) -> PresentationCompany:
    row = session.get(PresentationCompany, company_id)
    if row is None or row.workspace_id != workspace:
        raise HTTPException(404, "company not found")
    return row


def deck_of(session: Session, workspace: str, deck_id: str) -> PresentationDeck:
    row = session.get(PresentationDeck, deck_id)
    if row is None or row.workspace_id != workspace:
        raise HTTPException(404, "presentation not found")
    return row


def kit_of(session: Session, company_id: str, version: int | None) -> PresentationBrandKit:
    if version is None:
        raise HTTPException(409, "This company has no active brand kit yet. Create one first.")
    row = session.execute(select(PresentationBrandKit).where(PresentationBrandKit.company_id == company_id, PresentationBrandKit.version == version)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "brand kit version not found")
    return row


def canonical_sha(value: Any) -> str:
    import json

    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ----------------------------------------------------------------------------- capabilities


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "engine": engine.available(),
        "render": render.capabilities(),
        "genres": [{"id": k, "name": v} for k, v in genres.GENRES.items()],
        "slideTypes": ["cover", "section", "agenda", "statement", "bullets", "kpis", "chart", "table", "comparison", "timeline", "diagram", "decision", "quote", "closing"],
        "fonts": brandkit.SAFE_FONTS,
    }


# ----------------------------------------------------------------------------- companies and brand kits


class CompanyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


def company_out(session: Session, c: PresentationCompany) -> dict[str, Any]:
    versions = session.execute(select(func.count()).select_from(PresentationBrandKit).where(PresentationBrandKit.company_id == c.id)).scalar_one()
    active = None
    if c.active_brand_version:
        k = kit_of(session, c.id, c.active_brand_version)
        active = {"version": k.version, "sha256": k.sha256, "kit": k.kit_json, "warnings": k.warnings_json}
    return {"id": c.id, "name": c.name, "activeBrandVersion": c.active_brand_version, "brandVersions": versions, "activeBrand": active}


@router.post("/companies", status_code=201)
def create_company(body: CompanyIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    c = PresentationCompany(workspace_id=workspace, name=" ".join(body.name.split()))
    session.add(c)
    session.flush()
    return company_out(session, c)


@router.get("/companies")
def list_companies(workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    rows = session.execute(select(PresentationCompany).where(PresentationCompany.workspace_id == workspace).order_by(PresentationCompany.created_at)).scalars()
    return {"items": [company_out(session, c) for c in rows]}


@router.post("/companies/{company_id}/assets", status_code=201)
async def upload_asset(company_id: str, file: UploadFile = File(...), workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    company(session, workspace, company_id)
    data = await file.read(images.MAX_BYTES + 1)
    try:
        kind, w, h = images.inspect(data)
    except images.ImageError as exc:
        raise HTTPException(422, str(exc)) from exc
    digest = hashlib.sha256(data).hexdigest()
    existing = session.execute(select(PresentationAsset).where(PresentationAsset.company_id == company_id, PresentationAsset.sha256 == digest)).scalar_one_or_none()
    if existing is None:
        existing = PresentationAsset(workspace_id=workspace, company_id=company_id, sha256=digest, media_type=kind, width=w, height=h, byte_size=len(data), filename=re.sub(r"[^\w.\- ]", "_", file.filename or "logo")[:200], data=data)
        session.add(existing)
        session.flush()
    return {"id": existing.id, "sha256": digest, "mediaType": kind, "width": w, "height": h, "bytes": len(data)}


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)) -> Response:
    on()
    a = session.get(PresentationAsset, asset_id)
    if a is None or a.workspace_id != workspace:
        raise HTTPException(404, "asset not found")
    return Response(a.data, media_type=a.media_type, headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


class BrandIn(BaseModel):
    palette: dict[str, str] = Field(default_factory=dict)
    headingFont: str | None = Field(None, max_length=40)
    bodyFont: str | None = Field(None, max_length=40)
    footerText: str | None = Field(None, max_length=160)
    showPageNumber: bool = True
    seriesColors: list[str] | None = Field(None, max_length=6)
    logoAssetId: str | None = None
    darkLogoAssetId: str | None = None
    activate: bool = False


@router.post("/companies/{company_id}/brand-kits", status_code=201)
def create_brand_kit(company_id: str, body: BrandIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """A new immutable version. The first one becomes active; later ones only when asked."""
    on()
    c = company(session, workspace, company_id)
    logos = []
    for asset_id, variant in ((body.logoAssetId, "light_background"), (body.darkLogoAssetId, "dark_background")):
        if not asset_id:
            continue
        a = session.get(PresentationAsset, asset_id)
        if a is None or a.company_id != company_id:
            raise HTTPException(422, "logo must be an image uploaded for this company")
        variant = "universal" if not body.darkLogoAssetId else variant
        logos.append({"asset_id": a.id, "sha256": a.sha256, "variant": variant, "aspect_ratio": round(a.width / a.height, 4), "minimum_width_inches": 1.0, "clear_space_ratio": 0.2, "rights": "company_original"})
    latest = session.execute(select(func.max(PresentationBrandKit.version)).where(PresentationBrandKit.company_id == company_id)).scalar() or 0
    kit = brandkit.build(c.id, c.name, latest + 1, body.model_dump(), logos)
    try:
        warnings = engine.call({"op": "validate-kit", "kit": kit})["warnings"]
    except engine.EngineError as exc:
        raise problem(exc) from exc
    row = PresentationBrandKit(workspace_id=workspace, company_id=company_id, version=latest + 1, kit_json=kit, sha256=canonical_sha(kit), warnings_json=warnings)
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "another brand kit version was created at the same time; try again") from exc
    if body.activate or c.active_brand_version is None:
        c.active_brand_version = row.version
    return {"version": row.version, "sha256": row.sha256, "warnings": warnings, "active": c.active_brand_version == row.version, "kit": kit}


class ActivateIn(BaseModel):
    expectedActiveVersion: int | None = None


@router.post("/companies/{company_id}/brand-kits/{version}/activate")
def activate_brand_kit(company_id: str, version: int, body: ActivateIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Moves the active pointer only (compare-and-swap). Existing decks stay on their pinned version."""
    on()
    company(session, workspace, company_id)
    kit_of(session, company_id, version)
    moved = session.execute(
        update(PresentationCompany).where(PresentationCompany.id == company_id, PresentationCompany.active_brand_version.is_(body.expectedActiveVersion) if body.expectedActiveVersion is None else PresentationCompany.active_brand_version == body.expectedActiveVersion)
        .values(active_brand_version=version)
    ).rowcount
    if moved != 1:
        raise HTTPException(409, "the active brand kit changed meanwhile; reload")
    return {"activeBrandVersion": version}


# ----------------------------------------------------------------------------- starting points


class StarterIn(BaseModel):
    genre: str = Field(..., max_length=40)
    topic: str = Field("", max_length=200)
    periodLabel: str = Field("", max_length=80)
    audience: str = Field("", max_length=120)


@router.post("/starter")
def starter(body: StarterIn, workspace: str = Depends(access)) -> dict[str, Any]:
    on()
    try:
        return {"storyline": genres.storyline(body.genre, body.topic, body.periodLabel, body.audience), "mode": "template"}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ----------------------------------------------------------------------------- decks and revisions


def validate_storyline(storyline: dict[str, Any]) -> None:
    try:
        engine.call({"op": "validate-storyline", "storyline": storyline})
    except engine.EngineError as exc:
        raise problem(exc) from exc


def start_run(session: Session, background: BackgroundTasks, deck: PresentationDeck, revision: int) -> PresentationRun:
    run = PresentationRun(workspace_id=deck.workspace_id, deck_id=deck.id, revision=revision, status="queued", phase="queued", epoch=0, attempts=0)
    session.add(run)
    # Commit first: the build runs in its own session and must see the run and its revision.
    session.commit()
    background.add_task(worker.execute, run.id)
    return run


def run_out(run: PresentationRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {"id": run.id, "revision": run.revision, "status": run.status, "phase": run.phase, "error": run.error, "attempts": run.attempts}


def revision_out(session: Session, rev: PresentationRevision, full: bool = False) -> dict[str, Any]:
    arts = session.execute(select(PresentationArtifact).where(PresentationArtifact.deck_id == rev.deck_id, PresentationArtifact.revision == rev.revision).order_by(PresentationArtifact.kind, PresentationArtifact.position)).scalars().all()
    run = session.execute(select(PresentationRun).where(PresentationRun.deck_id == rev.deck_id, PresentationRun.revision == rev.revision).order_by(PresentationRun.created_at.desc())).scalars().first()
    out: dict[str, Any] = {
        "revision": rev.revision, "parent": rev.parent_revision, "state": rev.state, "author": rev.author,
        "brandVersion": rev.brand_version, "slideCount": rev.slide_count, "pptxSha256": rev.pptx_sha256, "error": rev.error,
        "createdAt": rev.created_at.isoformat() if rev.created_at else None,
        "approvedBy": rev.approved_by, "approvedAt": rev.approved_at.isoformat() if rev.approved_at else None,
        "quality": ({k: rev.receipt_json.get(k) for k in ("status", "hard_failures", "warnings", "slides_checked")} if rev.receipt_json else None),
        "files": {"pptx": any(a.kind == "pptx" for a in arts), "pdf": any(a.kind == "pdf" for a in arts), "slides": sum(1 for a in arts if a.kind == "png")},
        "run": run_out(run),
        "locks": rev.locks_json or [],
    }
    if full:
        out["storyline"] = rev.storyline_json
        out["findings"] = (rev.receipt_json or {}).get("findings", [])
        out["notes"] = [{"id": s["id"], "title": s["title"], "notes": s["notes"]["speaker_text"]} for s in (rev.deck_json or {}).get("slides", [])]
        out["receipt"] = rev.receipt_json
    return out


def deck_out(session: Session, d: PresentationDeck, full: bool = False) -> dict[str, Any]:
    head = session.get(PresentationRevision, (d.id, d.head_revision))
    out = {"id": d.id, "title": d.title, "companyId": d.company_id, "headRevision": d.head_revision, "archived": d.archived, "seriesId": d.series_id, "periodKey": d.period_key,
           "updatedAt": d.updated_at.isoformat() if d.updated_at else None, "head": revision_out(session, head, full) if head else None}
    if full:
        revs = session.execute(select(PresentationRevision).where(PresentationRevision.deck_id == d.id).order_by(PresentationRevision.revision.desc()).limit(50)).scalars()
        out["revisions"] = [revision_out(session, r) for r in revs]
    return out


class DeckIn(BaseModel):
    companyId: str
    storyline: dict[str, Any]


@router.post("/decks", status_code=202)
def create_deck(body: DeckIn, background: BackgroundTasks, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    c = company(session, workspace, body.companyId)
    kit_of(session, c.id, c.active_brand_version)
    validate_storyline(body.storyline)
    d = PresentationDeck(workspace_id=workspace, company_id=c.id, title=str(body.storyline["title"])[:200], head_revision=1)
    session.add(d)
    session.flush()
    session.add(PresentationRevision(deck_id=d.id, revision=1, brand_version=c.active_brand_version, author="person", storyline_json=body.storyline, locks_json=[], state="queued"))
    session.flush()
    run = start_run(session, background, d, 1)
    return {**deck_out(session, d), "run": run_out(run)}


@router.get("/decks")
def list_decks(workspace: str = Depends(access), session: Session = Depends(get_session), companyId: str | None = None, q: str | None = Query(None, max_length=100), archived: bool = False, limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    on()
    stmt = select(PresentationDeck).where(PresentationDeck.workspace_id == workspace, PresentationDeck.archived.is_(archived))
    if companyId:
        stmt = stmt.where(PresentationDeck.company_id == companyId)
    if q and q.strip():
        stmt = stmt.where(PresentationDeck.title.ilike("%" + q.strip().replace("%", "").replace("_", "") + "%"))
    rows = session.execute(stmt.order_by(PresentationDeck.updated_at.desc()).limit(limit)).scalars()
    return {"items": [deck_out(session, d) for d in rows]}


@router.get("/decks/{deck_id}")
def get_deck(deck_id: str, background: BackgroundTasks, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    d = deck_of(session, workspace, deck_id)
    for run_id in worker.recover(session, workspace):
        background.add_task(worker.execute, run_id)
    return deck_out(session, d, full=True)


@router.get("/decks/{deck_id}/revisions/{revision}")
def get_revision(deck_id: str, revision: int, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    deck_of(session, workspace, deck_id)
    rev = session.get(PresentationRevision, (deck_id, revision))
    if rev is None:
        raise HTTPException(404, "revision not found")
    return revision_out(session, rev, full=True)


class ReviseIn(BaseModel):
    storyline: dict[str, Any]
    expectedRevision: int = Field(..., ge=1)
    locks: list[str] = Field(default_factory=list, max_length=50)
    rebrand: bool = False  # move this deck to the company's current brand kit


def slide_map(storyline: dict[str, Any]) -> dict[str, Any]:
    return {s.get("id") or f"s{i + 1}": s for i, s in enumerate(storyline.get("slides", []))}


def new_revision(session: Session, background: BackgroundTasks, d: PresentationDeck, storyline: dict[str, Any], expected: int, locks: list[str], author: str, brand_version: int) -> dict[str, Any]:
    parent = session.get(PresentationRevision, (d.id, expected))
    if parent is None:
        raise HTTPException(404, "base revision not found")
    before, after = slide_map(parent.storyline_json), slide_map(storyline)
    for sid in parent.locks_json or []:
        if sid in before and before[sid] != after.get(sid):
            raise HTTPException(409, f"Slide “{before[sid].get('title', sid)}” is locked. Unlock it before changing or removing it.")
    revision = expected + 1
    moved = session.execute(
        update(PresentationDeck).where(PresentationDeck.id == d.id, PresentationDeck.head_revision == expected).values(head_revision=revision, title=str(storyline["title"])[:200], updated_at=datetime.now(timezone.utc))
    ).rowcount
    if moved != 1:
        raise HTTPException(409, "This presentation changed meanwhile. Reload to see the latest revision.")
    valid_locks = [x for x in dict.fromkeys(locks) if x in after]
    session.add(PresentationRevision(deck_id=d.id, revision=revision, parent_revision=expected, brand_version=brand_version, author=author, storyline_json=storyline, locks_json=valid_locks, state="queued"))
    session.flush()
    run = start_run(session, background, d, revision)
    session.refresh(d)
    return {**deck_out(session, d), "run": run_out(run)}


@router.post("/decks/{deck_id}/revisions", status_code=202)
def revise(deck_id: str, body: ReviseIn, background: BackgroundTasks, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Every change is a new revision built from scratch; earlier revisions and files never change."""
    on()
    d = deck_of(session, workspace, deck_id)
    validate_storyline(body.storyline)
    parent = session.get(PresentationRevision, (d.id, body.expectedRevision))
    c = company(session, workspace, d.company_id)
    version = c.active_brand_version if body.rebrand else (parent.brand_version if parent else c.active_brand_version)
    kit_of(session, c.id, version)
    return new_revision(session, background, d, body.storyline, body.expectedRevision, body.locks, "person", version)


class LocksIn(BaseModel):
    locks: list[str] = Field(default_factory=list, max_length=50)
    expectedRevision: int = Field(..., ge=1)


@router.post("/decks/{deck_id}/locks")
def set_locks(deck_id: str, body: LocksIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Locks are stored on the head revision (they describe the next edit, not the built file)."""
    on()
    d = deck_of(session, workspace, deck_id)
    if d.head_revision != body.expectedRevision:
        raise HTTPException(409, "This presentation changed meanwhile. Reload.")
    rev = session.get(PresentationRevision, (d.id, d.head_revision))
    known = slide_map(rev.storyline_json)
    rev.locks_json = [x for x in dict.fromkeys(body.locks) if x in known]
    return {"locks": rev.locks_json}


class RestoreIn(BaseModel):
    revision: int = Field(..., ge=1)
    expectedRevision: int = Field(..., ge=1)


@router.post("/decks/{deck_id}/restore", status_code=202)
def restore(deck_id: str, body: RestoreIn, background: BackgroundTasks, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    d = deck_of(session, workspace, deck_id)
    old = session.get(PresentationRevision, (d.id, body.revision))
    if old is None:
        raise HTTPException(404, "revision not found")
    head = session.get(PresentationRevision, (d.id, body.expectedRevision))
    if head is not None:
        head.locks_json = []  # restoring is an explicit choice to replace the content
    return new_revision(session, background, d, old.storyline_json, body.expectedRevision, old.locks_json or [], "person", old.brand_version)


@router.post("/decks/{deck_id}/archive")
def archive(deck_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    d = deck_of(session, workspace, deck_id)
    d.archived = not d.archived
    return {"archived": d.archived}


class ApproveIn(BaseModel):
    pptxSha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


@router.post("/decks/{deck_id}/revisions/{revision}/approve")
def approve(deck_id: str, revision: int, body: ApproveIn, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Binds approval to the exact file a reviewer saw. Hard quality failures cannot be approved."""
    on()
    workspace, role = access_role(request, session)
    if ROLE_RANK.get(role, -1) < ROLE_RANK["reviewer"]:
        raise HTTPException(403, "reviewer role required")
    deck_of(session, workspace, deck_id)
    rev = session.get(PresentationRevision, (deck_id, revision))
    if rev is None:
        raise HTTPException(404, "revision not found")
    if rev.state != "review_ready" or not rev.receipt_json or rev.receipt_json.get("hard_failures"):
        raise HTTPException(409, "Only a revision that passed its checks can be approved.")
    if rev.pptx_sha256 != body.pptxSha256:
        raise HTTPException(409, "The file changed since you reviewed it. Review the current file.")
    rev.state = "approved"
    rev.approved_by = request.headers.get("x-user-id") or role
    rev.approved_at = datetime.now(timezone.utc)
    return revision_out(session, rev)


FILE_TYPES = {"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pdf": "application/pdf", "png": "image/png"}


@router.get("/decks/{deck_id}/revisions/{revision}/files/{kind}")
def download(deck_id: str, revision: int, kind: str, workspace: str = Depends(access), session: Session = Depends(get_session), slide: int = Query(0, ge=0, le=60)) -> Response:
    on()
    d = deck_of(session, workspace, deck_id)
    if kind not in FILE_TYPES:
        raise HTTPException(404, "unknown file type")
    art = session.execute(
        select(PresentationArtifact).where(PresentationArtifact.deck_id == deck_id, PresentationArtifact.revision == revision, PresentationArtifact.kind == kind, PresentationArtifact.position == (slide if kind == "png" else 0))
    ).scalars().first()
    if art is None or art.workspace_id != workspace:
        raise HTTPException(404, "file not found")
    rev = session.get(PresentationRevision, (deck_id, revision))
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", d.title).strip("-")[:80] or "presentation"
    suffix = "" if rev and rev.state == "approved" else "-draft"
    headers = {"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff", "ETag": f'"{art.sha256}"'}
    if kind != "png":
        headers["Content-Disposition"] = f'attachment; filename="{stem}-r{revision}{suffix}.{kind}"'
    return Response(store.get(art.store_key), media_type=FILE_TYPES[kind], headers=headers)


@router.get("/runs/{run_id}")
def get_run(run_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    run = session.get(PresentationRun, run_id)
    if run is None or run.workspace_id != workspace:
        raise HTTPException(404, "run not found")
    return run_out(run)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    run = session.get(PresentationRun, run_id)
    if run is None or run.workspace_id != workspace:
        raise HTTPException(404, "run not found")
    if run.status in ("queued", "running"):
        session.execute(update(PresentationRun).where(PresentationRun.id == run_id).values(status="cancelled", phase="done", lease_expires_at=None))
        rev = session.get(PresentationRevision, (run.deck_id, run.revision))
        if rev and rev.state in ("queued", "composing"):
            rev.state, rev.error = "failed", "cancelled"
        session.refresh(run)
    return run_out(run)


# ----------------------------------------------------------------------------- weekly series


class SeriesIn(BaseModel):
    companyId: str
    name: str = Field(..., min_length=1, max_length=120)
    timezone: str = Field("UTC", max_length=60)
    weekStartsOn: int = Field(0, ge=0, le=6)
    rule: str = Field("previous_full_week", max_length=40)
    storyline: dict[str, Any]


def series_out(session: Session, s: PresentationSeries) -> dict[str, Any]:
    occ = session.execute(select(PresentationOccurrence).where(PresentationOccurrence.series_id == s.id).order_by(PresentationOccurrence.created_at.desc()).limit(20)).scalars().all()
    r = s.recipe_json
    try:
        nxt = weekly.period(r["rule"], r["timezone"], r["week_starts_on"])
    except ValueError:
        nxt = None
    return {"id": s.id, "name": s.name, "companyId": s.company_id, "version": s.version, "paused": s.paused, "timezone": r["timezone"], "rule": r["rule"], "weekStartsOn": r["week_starts_on"],
            "nextPeriod": nxt, "occurrences": [{"periodKey": o.period_key, "deckId": o.deck_id, "start": o.period_start, "end": o.period_end} for o in occ], "schedule": {"enabled": False, "note": "Drafts are prepared on request; automatic schedules are not enabled."}}


@router.post("/series", status_code=201)
def create_series(body: SeriesIn, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    c = company(session, workspace, body.companyId)
    kit_of(session, c.id, c.active_brand_version)
    try:
        weekly.period(body.rule, body.timezone, body.weekStartsOn)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    validate_storyline(body.storyline)
    s = PresentationSeries(workspace_id=workspace, company_id=c.id, name=" ".join(body.name.split()), version=1,
                           recipe_json={"rule": body.rule, "timezone": body.timezone, "week_starts_on": body.weekStartsOn, "storyline": body.storyline, "output_mode": "draft_only"})
    session.add(s)
    session.flush()
    return series_out(session, s)


@router.get("/series")
def list_series(workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    rows = session.execute(select(PresentationSeries).where(PresentationSeries.workspace_id == workspace).order_by(PresentationSeries.created_at)).scalars()
    return {"items": [series_out(session, s) for s in rows]}


class PrepareIn(BaseModel):
    at: datetime | None = None  # for previews and backfills; defaults to now


@router.post("/series/{series_id}/prepare", status_code=202)
def prepare(series_id: str, body: PrepareIn, background: BackgroundTasks, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Prepare this period's draft. Asking twice for the same period returns the same draft."""
    on()
    s = session.get(PresentationSeries, series_id)
    if s is None or s.workspace_id != workspace:
        raise HTTPException(404, "series not found")
    if s.paused:
        raise HTTPException(409, "This series is paused.")
    r = s.recipe_json
    p = weekly.period(r["rule"], r["timezone"], r["week_starts_on"], body.at)
    existing = session.execute(select(PresentationOccurrence).where(PresentationOccurrence.series_id == s.id, PresentationOccurrence.recipe_version == s.version, PresentationOccurrence.period_key == p["key"])).scalar_one_or_none()
    if existing:
        d = deck_of(session, workspace, existing.deck_id)
        return {"created": False, "period": p, "deck": deck_out(session, d)}
    prev = session.execute(select(PresentationOccurrence).where(PresentationOccurrence.series_id == s.id).order_by(PresentationOccurrence.created_at.desc())).scalars().first()
    base = r["storyline"]
    previous_label = None
    if prev:
        pd = session.get(PresentationDeck, prev.deck_id)
        last = session.get(PresentationRevision, (pd.id, pd.head_revision)) if pd else None
        if last:
            base, previous_label = last.storyline_json, prev.period_key
    storyline = weekly.carry_forward(base, p, previous_label)
    validate_storyline(storyline)
    c = company(session, workspace, s.company_id)
    kit_of(session, c.id, c.active_brand_version)
    d = PresentationDeck(workspace_id=workspace, company_id=c.id, title=str(storyline["title"])[:200], head_revision=1, series_id=s.id, period_key=p["key"])
    session.add(d)
    session.flush()
    try:
        with session.begin_nested():
            session.add(PresentationOccurrence(workspace_id=workspace, series_id=s.id, recipe_version=s.version, period_key=p["key"], period_start=p["start"], period_end=p["end_exclusive"], deck_id=d.id))
            session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.execute(select(PresentationOccurrence).where(PresentationOccurrence.series_id == s.id, PresentationOccurrence.recipe_version == s.version, PresentationOccurrence.period_key == p["key"])).scalar_one()
        return {"created": False, "period": p, "deck": deck_out(session, deck_of(session, workspace, existing.deck_id))}
    session.add(PresentationRevision(deck_id=d.id, revision=1, brand_version=c.active_brand_version, author="series", storyline_json=storyline, locks_json=[], state="queued"))
    session.flush()
    run = start_run(session, background, d, 1)
    return {"created": True, "period": p, "deck": {**deck_out(session, d), "run": run_out(run)}}


@router.post("/series/{series_id}/pause")
def pause(series_id: str, workspace: str = Depends(access), session: Session = Depends(get_session)) -> dict[str, Any]:
    on()
    s = session.get(PresentationSeries, series_id)
    if s is None or s.workspace_id != workspace:
        raise HTTPException(404, "series not found")
    s.paused = not s.paused
    return series_out(session, s)
