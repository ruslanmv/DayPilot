"""Automatic MCP tool classification (batch I5).

Classify a discovered tool as read / write / destructive from its name (and,
when present, MCP annotations). Administrators override per tool; the override
always wins. Classification drives the permission model: reads are allowed,
writes/destructive require approval.
"""
from __future__ import annotations

import re

from ..provider import CapabilityKind

_DESTRUCTIVE = {"delete", "remove", "drop", "destroy", "purge", "revoke", "wipe", "truncate"}
_WRITE = {
    "create", "update", "write", "post", "set", "send", "add", "insert", "modify",
    "edit", "patch", "put", "upsert", "assign", "move", "rename", "approve", "cancel",
}
_READ = {
    "get", "list", "search", "read", "fetch", "query", "describe", "status", "show",
    "find", "lookup", "count", "view", "resolve",
}


def _tokens(name: str) -> list[str]:
    # Split camelCase and snake/kebab/dot boundaries into lowercase words.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return [w.lower() for w in re.split(r"[^a-zA-Z]+", spaced) if w]


def classify_tool(name: str, annotations: dict | None = None) -> CapabilityKind:
    """Best-effort classification. Annotations (MCP `readOnlyHint`,
    `destructiveHint`) take priority over the name heuristic."""
    ann = annotations or {}
    if ann.get("destructiveHint") is True:
        return CapabilityKind.DESTRUCTIVE
    if ann.get("readOnlyHint") is True:
        return CapabilityKind.READ
    tokens = set(_tokens(name))
    if tokens & _DESTRUCTIVE:
        return CapabilityKind.DESTRUCTIVE
    if tokens & _READ and not tokens & _WRITE:
        return CapabilityKind.READ
    if tokens & _WRITE:
        return CapabilityKind.WRITE
    # Unknown verbs are treated as writes (safe default: require approval).
    return CapabilityKind.WRITE
