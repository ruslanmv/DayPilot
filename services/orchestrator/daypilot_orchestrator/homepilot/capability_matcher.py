"""Match a delegated sub-task to the best-suited worker agent (Batch A9).

Pure scoring over the safe, synced agent metadata (``capabilities_json``, role,
name) — no HomePilot call, no persona prompt. The delegation engine supplies the
eligible candidates (already filtered for same account, enabled, not the manager,
not an ancestor); this module just ranks them for the requested capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Candidate:
    link_id: str
    name: str
    role: str
    capabilities: list[str]


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def score(candidate: Candidate, needed: str) -> int:
    """Higher is better. Exact capability match dominates; role/name mentions and
    a non-empty capability list break ties. A candidate that can't be shown to
    match still scores 0 (eligible as a last resort)."""
    need = _norm(needed)
    if not need:
        return 1 if candidate.capabilities else 0
    caps = [_norm(c) for c in candidate.capabilities]
    s = 0
    if need in caps:
        s += 100
    if any(need in c or c in need for c in caps):
        s += 20
    if need in _norm(candidate.role):
        s += 10
    if need in _norm(candidate.name):
        s += 5
    return s


def match_worker(candidates: list[Candidate], needed: str) -> Candidate | None:
    """Return the best worker for ``needed``, or None if there are no candidates.
    Deterministic: ties break by name so the same input always picks the same
    worker."""
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda c: (-score(c, needed), _norm(c.name)))
    top = ranked[0]
    # With a concrete capability requested, require a real signal (>0). With no
    # capability, any eligible worker is acceptable.
    if _norm(needed) and score(top, needed) == 0:
        return None
    return top


def to_candidate(link: Any) -> Candidate:
    return Candidate(
        link_id=link.id,
        name=link.name or "",
        role=link.role or "",
        capabilities=list(link.capabilities_json or []),
    )
