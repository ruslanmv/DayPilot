"""Builds one deck revision: compose → export → render the actual file → check → publish.

Runs are fenced: a worker claims a run by bumping its lease epoch with a compare-and-swap, and may
publish only while that epoch is still current and the run is not cancelled. A stale worker that
finishes late writes nothing visible; artifacts are content-addressed files, so an abandoned write
is harmless. Failed builds leave earlier revisions and their downloads untouched.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from daypilot_knowledge.db.models import (
    PresentationArtifact,
    PresentationAsset,
    PresentationBrandKit,
    PresentationRevision,
    PresentationRun,
)

from . import engine, render, store

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3
log = logging.getLogger("daypilot.presentations")


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=None) if d and d.tzinfo else d


def claim(session: Session, run_id: str) -> int | None:
    """Take the lease. Returns the new epoch, or None when someone else holds a live lease."""
    run = session.get(PresentationRun, run_id, populate_existing=True)
    if run is None or run.status in ("succeeded", "failed", "cancelled"):
        return None
    if run.status == "running" and _naive(run.lease_expires_at) and _naive(run.lease_expires_at) > now():
        return None
    if run.attempts >= MAX_ATTEMPTS:
        session.execute(update(PresentationRun).where(PresentationRun.id == run_id).values(status="failed", error="gave up after repeated interruptions"))
        session.commit()
        return None
    epoch = run.epoch + 1
    won = session.execute(
        update(PresentationRun)
        .where(PresentationRun.id == run_id, PresentationRun.epoch == run.epoch)
        .values(status="running", epoch=epoch, lease_expires_at=now() + LEASE, attempts=run.attempts + 1, phase="compose")
    ).rowcount
    session.commit()
    return epoch if won == 1 else None


def _phase(session: Session, run_id: str, epoch: int, phase: str) -> bool:
    ok = session.execute(
        update(PresentationRun)
        .where(PresentationRun.id == run_id, PresentationRun.epoch == epoch, PresentationRun.status == "running")
        .values(phase=phase, lease_expires_at=now() + LEASE)
    ).rowcount == 1
    session.commit()
    return ok


def assets_for(session: Session, kit: dict[str, Any], company_id: str) -> dict[str, Any]:
    ids = [logo["asset_id"] for logo in kit.get("logos", [])]
    out: dict[str, Any] = {}
    for asset in session.execute(select(PresentationAsset).where(PresentationAsset.company_id == company_id, PresentationAsset.id.in_(ids))).scalars():
        out[asset.id] = {"media_type": asset.media_type, "base64": base64.b64encode(asset.data).decode(), "width": asset.width, "height": asset.height}
    return out


def build(session: Session, run_id: str) -> str:
    """Execute a run to completion. Returns the final run status."""
    epoch = claim(session, run_id)
    if epoch is None:
        return session.get(PresentationRun, run_id, populate_existing=True).status if session.get(PresentationRun, run_id, populate_existing=True) else "missing"
    run = session.get(PresentationRun, run_id, populate_existing=True)
    rev = session.get(PresentationRevision, (run.deck_id, run.revision), populate_existing=True)
    kit_row = session.execute(
        select(PresentationBrandKit).where(PresentationBrandKit.company_id == _company(session, run), PresentationBrandKit.version == rev.brand_version)
    ).scalar_one()
    rev.state = "composing"
    session.commit()
    kit = kit_row.kit_json
    try:
        composed = engine.call({"op": "compose", "storyline": rev.storyline_json, "kit": kit, "options": {
            "deckId": run.deck_id, "workspaceId": run.workspace_id,
            "templateRef": {"id": f"{kit['id']}_curated", "version": kit["version"], "sha256": kit_row.sha256},
        }})
        deck, compose_findings = composed["deck"], composed["findings"]
        if not _phase(session, run_id, epoch, "export"):
            return "stale"
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(prefix="dp-deck-") as tmp:
            out = str(Path(tmp) / "deck.pptx")
            built = engine.call({"op": "compile", "deck": deck, "kit": kit, "assets": assets_for(session, kit, kit_row.company_id), "out": out})
            pptx = Path(out).read_bytes()
        receipt = built["receipt"]
        receipt["findings"] = compose_findings + [f for f in receipt["findings"] if not any(f.get("code") == c.get("code") and f.get("element") == c.get("element") for c in compose_findings)]
        if not _phase(session, run_id, epoch, "render"):
            return "stale"
        rendered = None
        try:
            rendered = render.render(pptx)
            receipt["checks"].append("actual_render")
            if len(rendered.pages) != len(deck["slides"]):
                receipt["findings"].append({"severity": "hard", "code": "render_pages", "slide": None, "message": f"The rendered file has {len(rendered.pages)} pages; the deck has {len(deck['slides'])} slides."})
            for page in rendered.blank:
                receipt["findings"].append({"severity": "hard", "code": "blank_render", "slide": deck["slides"][page - 1]["id"], "message": f"Slide {page} rendered blank."})
        except Exception as exc:  # noqa: BLE001 - a missing renderer is reported, not hidden
            receipt["findings"].append({"severity": "warning", "code": "not_rendered", "slide": None, "message": f"The exported file could not be rendered for review ({type(exc).__name__}). Install the render worker to check it."})
        hard = sum(1 for f in receipt["findings"] if f["severity"] == "hard")
        receipt["hard_failures"], receipt["warnings"] = hard, len(receipt["findings"]) - hard
        receipt["status"] = "failed" if hard else ("passed" if rendered else "unverified")
        receipt["render"] = {"rendered": bool(rendered), **render.capabilities()}
        if not _phase(session, run_id, epoch, "publish"):
            return "stale"
        files = [("pptx", 0, pptx)]
        if rendered:
            files.append(("pdf", 0, rendered.pdf))
            files += [("png", i + 1, png) for i, png in enumerate(rendered.pages)]
        written = [(kind, pos, *store.put(run.workspace_id, kind, data), len(data)) for kind, pos, data in files]
        # Publication: one transaction, guarded by the lease epoch.
        still_mine = session.execute(
            update(PresentationRun).where(PresentationRun.id == run_id, PresentationRun.epoch == epoch, PresentationRun.status == "running")
            .values(status="succeeded", phase="done", lease_expires_at=None)
        ).rowcount == 1
        if not still_mine:
            session.rollback()
            return "stale"
        for kind, pos, digest, key, size in written:
            session.add(PresentationArtifact(workspace_id=run.workspace_id, deck_id=run.deck_id, revision=run.revision, kind=kind, position=pos, sha256=digest, byte_size=size, store_key=key, run_id=run_id))
        rev.deck_json = deck
        rev.receipt_json = receipt
        rev.pptx_sha256 = built["sha256"]
        rev.slide_count = len(deck["slides"])
        rev.state = "failed" if hard else "review_ready"
        rev.error = None
        session.commit()
        return "succeeded"
    except engine.EngineError as exc:
        session.rollback()
        message = ("; ".join(exc.problems[:5]) or str(exc))[:500]
        done = session.execute(
            update(PresentationRun).where(PresentationRun.id == run_id, PresentationRun.epoch == epoch, PresentationRun.status == "running")
            .values(status="failed", phase="done", error=message, lease_expires_at=None)
        ).rowcount == 1
        if done:
            rev.state, rev.error = "failed", message
        session.commit()
        return "failed"


def _company(session: Session, run: PresentationRun) -> str:
    from daypilot_knowledge.db.models import PresentationDeck

    return session.get(PresentationDeck, run.deck_id).company_id


def execute(run_id: str) -> None:
    """Background entry point with its own session."""
    from ..db import _get_sessionmaker

    with _get_sessionmaker()() as session:
        try:
            build(session, run_id)
        except Exception:  # noqa: BLE001 - never crash the server thread; the lease expires and recovery retries
            log.exception("presentation run %s crashed", run_id)


def recover(session: Session, workspace_id: str) -> list[str]:
    """Runs whose worker vanished (lease expired) are queued again, bounded by MAX_ATTEMPTS."""
    stale = session.execute(
        select(PresentationRun.id).where(PresentationRun.workspace_id == workspace_id, PresentationRun.status == "running", PresentationRun.lease_expires_at < now())
    ).scalars().all()
    return list(stale)
