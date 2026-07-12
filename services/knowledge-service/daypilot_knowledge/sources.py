"""Document source permissions (batch B10).

Default posture is read + index only. A local folder or Box scope must be
explicitly granted before DayPilot will ingest from it — no scanning outside a
granted scope, no destructive edits, no external sharing without approval.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PERMISSION_READ_INDEX = "read_index"
PERMISSION_READ_GENERATE = "read_generate"  # may write new-version outputs to the Vault


@dataclass(frozen=True)
class SourceGrant:
    kind: str  # local | box | project_vault
    scope: str  # folder path or Box folder id
    permission: str = PERMISSION_READ_INDEX


class SourceRegistry:
    """In-memory grant registry seeded from env; a real deployment persists it."""

    def __init__(self) -> None:
        self._grants: list[SourceGrant] = []
        self._load_env()

    def _load_env(self) -> None:
        # DAYPILOT_LOCAL_SOURCES="/data/projects,/data/contracts"
        raw = os.getenv("DAYPILOT_LOCAL_SOURCES", "")
        for folder in filter(None, (f.strip() for f in raw.split(","))):
            self._grants.append(SourceGrant(kind="local", scope=folder))
        # The DayPilot Vault is always a permitted generate target.
        self._grants.append(
            SourceGrant(kind="project_vault", scope="vault://", permission=PERMISSION_READ_GENERATE)
        )

    def grant(self, kind: str, scope: str, permission: str = PERMISSION_READ_INDEX) -> SourceGrant:
        g = SourceGrant(kind=kind, scope=scope, permission=permission)
        self._grants.append(g)
        return g

    def grants(self) -> list[SourceGrant]:
        return list(self._grants)

    def is_permitted(self, path: str) -> bool:
        # Vault and explicitly granted local folders (by prefix) are allowed.
        if path.startswith("vault://"):
            return True
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError):
            return False
        for grant in self._grants:
            if grant.kind == "local":
                try:
                    if str(resolved).startswith(str(Path(grant.scope).resolve())):
                        return True
                except (OSError, ValueError):
                    continue
        return False

    def can_generate(self, target: str) -> bool:
        if target.startswith("vault://"):
            return True
        for grant in self._grants:
            if grant.permission == PERMISSION_READ_GENERATE and target.startswith(grant.scope):
                return True
        return False


_registry: SourceRegistry | None = None


def get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry
