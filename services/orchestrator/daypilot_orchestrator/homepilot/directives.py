"""Validation of untrusted persona directives (Batch A7).

``x_directives`` comes from a language model on the other side of the bridge — it
is UNTRUSTED input and the security surface of the whole integration. HomePilot
already validates on its side, but DayPilot re-validates from scratch here
(defense in depth, contract rule 7): a directive is accepted only if its type is
in the allowed set, its capability (for an external-write proposal) is in the
allowed set, and its arguments fit the length/priority/percent bounds. Anything
else is rejected with a reason while the rest of the turn is preserved.

This module is pure — no database, no side effects. Workspace/agent ownership of
referenced tasks is enforced later, in the task mapper, where the DB is
available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    ALLOWED_DIRECTIVES,
    AUTO_APPLY_DIRECTIVES,
    CAPABILITIES,
    MAX_DIRECTIVES_PER_TURN,
    MAX_TEXT_LEN,
    MAX_TITLE_LEN,
    VALID_PRIORITIES,
)

# Directive types that reference an existing task (validated for ownership later).
_TASK_REF_TYPES = frozenset({"task.update", "task.complete", "task.block", "progress.report"})


@dataclass
class Directive:
    """One validated, sanitized directive ready for the mapper."""

    type: str
    title: str = ""
    detail: str = ""
    priority: str = "medium"
    percent: int | None = None
    capability: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    ref: str | None = None  # a client-supplied handle to a prior/related task

    @property
    def auto_apply(self) -> bool:
        """True when the directive only tracks internal work (no outside-world
        effect) and may be applied without an approval."""
        return self.type in AUTO_APPLY_DIRECTIVES

    @property
    def references_task(self) -> bool:
        return self.type in _TASK_REF_TYPES


@dataclass
class Rejection:
    index: int
    type: str
    reason: str


@dataclass
class ValidationResult:
    directives: list[Directive] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {"accepted": len(self.directives), "rejected": len(self.rejected)}


def _clip(value: Any, limit: int) -> str:
    return str(value)[:limit] if value is not None else ""


def _items(x_directives: Any) -> list[Any]:
    """Accept either ``{"items": [...]}`` / ``{"directives": [...]}`` or a bare list."""
    if isinstance(x_directives, dict):
        items = x_directives.get("items")
        if items is None:
            items = x_directives.get("directives")
        return items if isinstance(items, list) else []
    if isinstance(x_directives, list):
        return x_directives
    return []


def _validate_one(index: int, raw: Any) -> tuple[Directive | None, Rejection | None]:
    if not isinstance(raw, dict):
        return None, Rejection(index, "?", "not_an_object")
    dtype = str(raw.get("type") or "").strip()
    if dtype not in ALLOWED_DIRECTIVES:
        return None, Rejection(index, dtype or "?", "type_not_allowed")

    d = Directive(type=dtype)
    d.title = _clip(raw.get("title") or raw.get("summary"), MAX_TITLE_LEN)
    d.detail = _clip(raw.get("detail") or raw.get("text"), MAX_TEXT_LEN)

    priority = str(raw.get("priority") or "").strip().lower()
    d.priority = priority if priority in VALID_PRIORITIES else "medium"

    if "percent" in raw or "progress" in raw:
        try:
            d.percent = max(0, min(100, int(raw.get("percent", raw.get("progress")))))
        except (TypeError, ValueError):
            d.percent = None

    if raw.get("ref"):
        d.ref = _clip(raw.get("ref"), 120)

    if dtype == "delegate.request":
        # A free-form skill/role to match a worker agent (not a DayPilot
        # capability). Optional — the matcher falls back to any eligible worker.
        d.capability = _clip(raw.get("capability") or raw.get("to") or raw.get("role"), 120)

    if dtype == "daypilot.action.propose":
        capability = str(raw.get("capability") or "").strip()
        if capability not in CAPABILITIES:
            return None, Rejection(index, dtype, "capability_not_allowed")
        d.capability = capability
        if not d.title:
            d.title = _clip(raw.get("summary") or capability, MAX_TITLE_LEN)
        args = raw.get("arguments")
        # Arguments are opaque here and are only ever *proposed* — never executed
        # by this validator. The Approval Center / executor validates them per
        # capability when the user approves. We only bound the shape.
        if isinstance(args, dict) and len(args) <= 50:
            d.arguments = args

    if dtype in _TASK_REF_TYPES and not d.ref:
        # A task-mutating directive with no target is unusable.
        return None, Rejection(index, dtype, "missing_task_ref")

    if dtype == "task.create" and not d.title:
        return None, Rejection(index, dtype, "missing_title")

    return d, None


def validate_directives(x_directives: Any) -> ValidationResult:
    """Validate an untrusted ``x_directives`` payload into safe directives.

    Caps the number of accepted directives at ``MAX_DIRECTIVES_PER_TURN``;
    anything beyond that is rejected as ``over_limit`` so the surface can never be
    flooded.
    """
    result = ValidationResult()
    for i, raw in enumerate(_items(x_directives)):
        if len(result.directives) >= MAX_DIRECTIVES_PER_TURN:
            dtype = raw.get("type", "?") if isinstance(raw, dict) else "?"
            result.rejected.append(Rejection(i, str(dtype), "over_limit"))
            continue
        directive, rejection = _validate_one(i, raw)
        if directive is not None:
            result.directives.append(directive)
        elif rejection is not None:
            result.rejected.append(rejection)
    return result
