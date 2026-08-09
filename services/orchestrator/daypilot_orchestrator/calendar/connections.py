"""Which calendars are connected, and how fresh they are.

`planner_readiness` used to answer "is a calendar connected?" with
``email_enabled()`` — the *email* feature flag. This module answers it by
looking at the workspace's actual calendar connections, so the Planning surface
and the Calendar header can say something true.

Calendar providers are ordinary Integration Gateway providers, so a connection
is an ``IntegrationConnection`` row like Slack's or GitHub's. Nothing here
touches credentials: those live in the secrets backend keyed by connection id.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import IntegrationConnection

#: Canonical provider ids. `calendar` is the pre-rename Google registration and
#: is still resolved so existing connections keep working.
MICROSOFT = "microsoft_calendar"
GOOGLE = "google_calendar"
LEGACY_GOOGLE = "calendar"

CALENDAR_PROVIDERS = (MICROSOFT, GOOGLE, LEGACY_GOOGLE)

PROVIDER_LABELS = {
    MICROSOFT: "Microsoft Outlook",
    GOOGLE: "Google Calendar",
    LEGACY_GOOGLE: "Google Calendar",
}

#: A calendar that has not synced within this window is stale enough that the
#: plan built from it should not be described as current.
FRESH_MINUTES = 30
STALE_MINUTES = 24 * 60


def canonical_provider(provider: str) -> str:
    """Map the legacy `calendar` registration onto its real identity."""
    return GOOGLE if provider == LEGACY_GOOGLE else provider


def freshness(last_sync_at: datetime | None, now: datetime | None = None) -> str:
    """fresh | stale | never — how much to trust what the store holds."""
    if last_sync_at is None:
        return "never"
    reference = now or datetime.utcnow()
    age = reference - last_sync_at
    if age <= timedelta(minutes=FRESH_MINUTES):
        return "fresh"
    if age <= timedelta(minutes=STALE_MINUTES):
        return "stale"
    return "stale"


def list_connections(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    """Every calendar connection the workspace has, newest activity first."""
    rows = session.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.provider.in_(CALENDAR_PROVIDERS),
        )
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for row in rows:
        provider = canonical_provider(row.provider)
        out.append({
            "id": row.id,
            "provider": provider,
            "label": PROVIDER_LABELS.get(row.provider, provider),
            "status": row.status,
            "account": (row.detail or "").strip() or None,
            "capabilities": list(row.capabilities or []),
            "lastSyncAt": row.last_activity_at.isoformat() if row.last_activity_at else None,
            "freshness": freshness(row.last_activity_at),
            # Writes are approval-gated for every calendar provider; stating it
            # here keeps the UI from having to infer the governance model.
            "writesRequireApproval": True,
        })
    out.sort(key=lambda c: (c["lastSyncAt"] or ""), reverse=True)
    return out


def status(session: Session, workspace_id: str = "default") -> dict[str, Any]:
    """The Calendar header's and the planner's shared view of connectivity."""
    connections = list_connections(session, workspace_id)
    live = [c for c in connections if c["status"] == "connected"]
    last = max((c["lastSyncAt"] for c in live if c["lastSyncAt"]), default=None)
    return {
        "connected": bool(live),
        "providers": sorted({c["provider"] for c in live}),
        "connections": connections,
        "lastSyncAt": last,
        "freshness": freshness(datetime.fromisoformat(last)) if last else "never",
        "available": [
            {"provider": MICROSOFT, "label": PROVIDER_LABELS[MICROSOFT]},
            {"provider": GOOGLE, "label": PROVIDER_LABELS[GOOGLE]},
        ],
    }


def connected_providers(session: Session, workspace_id: str = "default") -> set[str]:
    """Every connected provider in the workspace — not just calendars.

    The meeting-context allow-list needs this: granting Slack context means
    nothing unless Slack is actually connected.
    """
    rows = session.execute(
        select(IntegrationConnection.provider).where(
            IntegrationConnection.workspace_id == workspace_id,
            IntegrationConnection.status == "connected",
        )
    ).scalars().all()
    return {canonical_provider(p) for p in rows}
