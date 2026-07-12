"""Per-capability permission model (batch I0/I1).

Safe by default: reads are allowed, writes and destructive actions require an
approval. An administrator can override a specific capability on a connection
(stored in `IntegrationConnection.permissions_json`).
"""
from __future__ import annotations

from enum import Enum

from .provider import CapabilityKind


class Permission(str, Enum):
    ALLOWED = "allowed"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


DEFAULT_PERMISSION: dict[CapabilityKind, Permission] = {
    CapabilityKind.READ: Permission.ALLOWED,
    CapabilityKind.WRITE: Permission.APPROVAL_REQUIRED,
    CapabilityKind.DESTRUCTIVE: Permission.APPROVAL_REQUIRED,
}


def resolve_permission(kind: CapabilityKind, overrides: dict[str, str] | None, capability_id: str) -> Permission:
    """Return the effective permission for a capability, applying any override."""
    if overrides and capability_id in overrides:
        try:
            return Permission(overrides[capability_id])
        except ValueError:
            pass
    return DEFAULT_PERMISSION.get(kind, Permission.APPROVAL_REQUIRED)


# Risk label surfaced on approvals, by capability kind.
RISK_BY_KIND: dict[CapabilityKind, str] = {
    CapabilityKind.READ: "low",
    CapabilityKind.WRITE: "medium",
    CapabilityKind.DESTRUCTIVE: "high",
}
