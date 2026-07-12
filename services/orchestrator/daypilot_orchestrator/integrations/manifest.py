"""Integration manifests + curated catalog (batch I9).

Turns the internal integration system into a controlled platform. Every
integration declares a manifest; the catalog is curated (not public) with tiers,
and workspace administrators decide what is enabled. Third parties/internal teams
can install a manifest without changing the core.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Curation tiers, most-trusted first.
TIERS = ("verified", "certified", "private", "experimental")
VALID_TRANSPORTS = {"streamable-http", "streamable_http", "stdio", "native"}
VALID_RISK = {"low", "medium", "high"}
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class IntegrationManifest:
    id: str
    name: str
    version: str
    publisher: str
    transport: str
    capabilities: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    risk: str = "medium"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_manifest(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (ok, errors). Cheap structural validation before certification."""
    errors: list[str] = []
    for f in ("id", "name", "version", "publisher", "transport"):
        if not data.get(f):
            errors.append(f"missing required field: {f}")
    if data.get("transport") and data["transport"] not in VALID_TRANSPORTS:
        errors.append(f"invalid transport: {data['transport']}")
    if data.get("risk", "medium") not in VALID_RISK:
        errors.append(f"invalid risk: {data.get('risk')}")
    caps = data.get("capabilities")
    if not isinstance(caps, list) or not caps:
        errors.append("capabilities must be a non-empty list")
    if data.get("version") and not _SEMVER.match(str(data["version"])):
        errors.append("version must be semver (x.y.z)")
    return (not errors, errors)


# id -> {"manifest": {...}, "tier": str, "certified": bool}
_CATALOG: dict[str, dict[str, Any]] = {}


def register_manifest(data: dict[str, Any], tier: str = "experimental", certified: bool = False) -> dict[str, Any]:
    ok, errors = validate_manifest(data)
    if not ok:
        raise ValueError("; ".join(errors))
    if tier not in TIERS:
        raise ValueError(f"invalid tier: {tier}")
    _CATALOG[data["id"]] = {"manifest": data, "tier": tier, "certified": certified}
    return _CATALOG[data["id"]]


def get_entry(manifest_id: str) -> dict[str, Any] | None:
    return _CATALOG.get(manifest_id)


def set_certified(manifest_id: str, certified: bool, tier: str | None = None) -> dict[str, Any]:
    entry = _CATALOG[manifest_id]
    entry["certified"] = certified
    if tier is not None:
        entry["tier"] = tier
    return entry


def list_catalog(tier: str | None = None) -> list[dict[str, Any]]:
    entries = [
        {"id": e["manifest"]["id"], "name": e["manifest"]["name"], "version": e["manifest"]["version"],
         "publisher": e["manifest"]["publisher"], "risk": e["manifest"].get("risk", "medium"),
         "tier": e["tier"], "certified": e["certified"]}
        for e in _CATALOG.values()
    ]
    if tier:
        entries = [e for e in entries if e["tier"] == tier]
    order = {t: i for i, t in enumerate(TIERS)}
    return sorted(entries, key=lambda e: (order.get(e["tier"], 99), e["name"]))


def _seed_curated() -> None:
    """A curated (not public) starter catalog."""
    curated = [
        ({"id": "slack", "name": "Slack", "version": "1.0.0", "publisher": "DayPilot",
          "transport": "native", "capabilities": ["chat.read", "chat.send"],
          "events": ["mention.created", "message.received"], "risk": "medium"}, "verified", True),
        ({"id": "github", "name": "GitHub", "version": "1.0.0", "publisher": "DayPilot",
          "transport": "native", "capabilities": ["repo.read", "checks.read", "pr.create"],
          "events": ["comment.created", "task.updated"], "risk": "medium"}, "verified", True),
        ({"id": "google-calendar", "name": "Google Calendar", "version": "1.0.0", "publisher": "DayPilot",
          "transport": "native", "capabilities": ["events.read", "events.write"],
          "events": ["task.updated"], "risk": "medium"}, "verified", True),
        ({"id": "notion", "name": "Notion", "version": "0.9.0", "publisher": "DayPilot Partners",
          "transport": "streamable-http", "capabilities": ["page.read", "page.update"],
          "events": ["comment.created"], "risk": "medium"}, "certified", True),
        ({"id": "company-crm", "name": "Company CRM", "version": "1.2.0", "publisher": "Internal Platform Team",
          "transport": "streamable-http", "capabilities": ["customer.search", "customer.read", "customer.update"],
          "events": ["customer.created", "customer.updated"], "risk": "medium"}, "private", True),
    ]
    for data, tier, certified in curated:
        register_manifest(data, tier=tier, certified=certified)


_seed_curated()
