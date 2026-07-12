"""Daily plan lifecycle state machine (batch B4).

A DayPilot day plan moves through a small, explicit set of states so the user
always knows whether AI is still proposing, whether they have approved, and
whether the day is running or wrapped:

    DRAFT -> PROPOSED -> APPROVED -> ACTIVE -> WRAPPED
                 |           |          |
                 +----> ADJUSTED <------+  (re-approve / re-activate)

Adjustments (user edits the AI proposal via chat) route through ADJUSTED and
back, so an approved or active plan is never silently mutated.
"""
from __future__ import annotations

from enum import StrEnum


class PlanState(StrEnum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    ADJUSTED = "ADJUSTED"
    WRAPPED = "WRAPPED"


class PlanAction(StrEnum):
    PROPOSE = "propose"
    APPROVE = "approve"
    ADJUST = "adjust"
    ACTIVATE = "activate"
    WRAP = "wrap"
    REDRAFT = "redraft"


# Allowed (from_state, action) -> to_state transitions.
_TRANSITIONS: dict[tuple[PlanState, PlanAction], PlanState] = {
    (PlanState.DRAFT, PlanAction.PROPOSE): PlanState.PROPOSED,
    (PlanState.PROPOSED, PlanAction.APPROVE): PlanState.APPROVED,
    (PlanState.PROPOSED, PlanAction.ADJUST): PlanState.ADJUSTED,
    (PlanState.PROPOSED, PlanAction.REDRAFT): PlanState.DRAFT,
    (PlanState.APPROVED, PlanAction.ACTIVATE): PlanState.ACTIVE,
    (PlanState.APPROVED, PlanAction.ADJUST): PlanState.ADJUSTED,
    (PlanState.ADJUSTED, PlanAction.APPROVE): PlanState.APPROVED,
    (PlanState.ADJUSTED, PlanAction.ACTIVATE): PlanState.ACTIVE,
    (PlanState.ACTIVE, PlanAction.ADJUST): PlanState.ADJUSTED,
    (PlanState.ACTIVE, PlanAction.WRAP): PlanState.WRAPPED,
}

TERMINAL_STATES = frozenset({PlanState.WRAPPED})


class InvalidPlanTransition(ValueError):
    """Raised when an action is not permitted from the current plan state."""


def allowed_actions(state: PlanState | str) -> list[PlanAction]:
    current = PlanState(state)
    return [action for (frm, action) in _TRANSITIONS if frm == current]


def next_state(state: PlanState | str, action: PlanAction | str) -> PlanState:
    """Return the resulting state, or raise InvalidPlanTransition."""
    current = PlanState(state)
    act = PlanAction(action)
    target = _TRANSITIONS.get((current, act))
    if target is None:
        raise InvalidPlanTransition(
            f"Cannot '{act}' a plan in state '{current}'. Allowed: "
            f"{', '.join(a.value for a in allowed_actions(current)) or 'none'}"
        )
    return target


def is_terminal(state: PlanState | str) -> bool:
    return PlanState(state) in TERMINAL_STATES
