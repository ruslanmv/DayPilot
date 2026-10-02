"""AI credits: metering for AI actions that run on the workspace's own connected models.

Off unless ``DAYPILOT_AI_CREDITS=true`` (then AI behaves exactly as before: unmetered). When on, each
action costs credits taken atomically before the model is called, so concurrent requests can never
overspend; a request that fails or finds no provider is refunded. The balance refills to the monthly
allowance at the start of each month. The ledger records the action and amounts, never prompt text.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daypilot_knowledge.db.models import AiCreditAccount, AiCreditEvent

DEFAULT_COSTS = {"chat": 1, "generate": 2, "grow": 1, "explain": 1, "reorganize": 2, "refine": 1}
MAX_GRANT = 1_000_000


def enabled() -> bool:
    return os.getenv("DAYPILOT_AI_CREDITS", "false").lower() == "true"


def default_allowance() -> int:
    try:
        return max(0, min(MAX_GRANT, int(os.getenv("DAYPILOT_AI_MONTHLY_CREDITS", "100"))))
    except ValueError:
        return 100


def costs() -> dict[str, int]:
    table = dict(DEFAULT_COSTS)
    try:
        override = json.loads(os.getenv("DAYPILOT_AI_CREDIT_COSTS", "") or "{}")
    except ValueError:
        override = {}
    for key, value in (override.items() if isinstance(override, dict) else []):
        if key in table and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
            table[key] = value
    return table


def cost_for(action: str, focus_count: int = 0) -> int:
    base = costs().get(action, 1)
    # Acting on many topics at once is a bigger job: one more credit per five beyond the first five.
    extra = min(5, max(0, (focus_count - 1) // 5)) if action in ("refine", "grow", "explain") else 0
    return base + extra if base else 0


def month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _log(session: Session, ws: str, kind: str, action: str | None, amount: int, after: int) -> None:
    session.add(AiCreditEvent(workspace_id=ws, kind=kind, action=action, amount=amount, balance_after=after))


def account(session: Session, ws: str) -> AiCreditAccount:
    """The workspace's account, created with the default allowance, refilled when a new month began."""
    row = session.get(AiCreditAccount, ws)
    if row is None:
        row = AiCreditAccount(workspace_id=ws, balance=default_allowance(), monthly_allowance=default_allowance(), period=month())
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            _log(session, ws, "refill", None, row.balance, row.balance)
        except IntegrityError:
            row = session.get(AiCreditAccount, ws)  # created by a concurrent request
    elif row.period != month():
        topped = max(row.balance, row.monthly_allowance)
        gained = topped - row.balance
        session.execute(update(AiCreditAccount).where(AiCreditAccount.workspace_id == ws).values(balance=topped, period=month()))
        session.refresh(row)
        if gained:
            _log(session, ws, "refill", None, gained, topped)
    assert row is not None
    return row


def charge(session: Session, ws: str, action: str, cost: int) -> int:
    """Take ``cost`` credits atomically or raise 402. Returns the new balance."""
    acct = account(session, ws)
    if cost <= 0:
        return acct.balance
    taken = session.execute(
        update(AiCreditAccount)
        .where(AiCreditAccount.workspace_id == ws, AiCreditAccount.balance >= cost)
        .values(balance=AiCreditAccount.balance - cost)
    )
    if taken.rowcount != 1:
        session.refresh(acct)
        raise HTTPException(402, f"Not enough AI credits: this needs {cost}, you have {acct.balance}. Ask a workspace owner to add credits.")
    session.refresh(acct)
    _log(session, ws, "use", action, -cost, acct.balance)
    return acct.balance


def refund(session: Session, ws: str, action: str, cost: int) -> int:
    acct = account(session, ws)
    if cost > 0:
        session.execute(update(AiCreditAccount).where(AiCreditAccount.workspace_id == ws).values(balance=AiCreditAccount.balance + cost))
        session.refresh(acct)
        _log(session, ws, "refund", action, cost, acct.balance)
    return acct.balance


def grant(session: Session, ws: str, amount: int, allowance: int | None = None) -> AiCreditAccount:
    acct = account(session, ws)
    values: dict[str, Any] = {}
    if amount:
        values["balance"] = AiCreditAccount.balance + amount
    if allowance is not None:
        values["monthly_allowance"] = allowance
    if values:
        session.execute(update(AiCreditAccount).where(AiCreditAccount.workspace_id == ws).values(**values))
        session.refresh(acct)
    if amount:
        _log(session, ws, "grant", None, amount, acct.balance)
    return acct


def summary(session: Session, ws: str) -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "costs": costs()}
    acct = account(session, ws)
    events = session.execute(
        select(AiCreditEvent).where(AiCreditEvent.workspace_id == ws).order_by(AiCreditEvent.created_at.desc()).limit(20)
    ).scalars()
    return {
        "enabled": True,
        "balance": acct.balance,
        "monthlyAllowance": acct.monthly_allowance,
        "costs": costs(),
        "recent": [
            {"kind": e.kind, "action": e.action, "amount": e.amount, "balanceAfter": e.balance_after, "at": e.created_at.isoformat() if e.created_at else None}
            for e in events
        ],
    }
