"""Opaque keyset (cursor) pagination for large DayPilot ledgers.

Cursor pagination keeps list latency flat as tables grow to thousands of rows,
because each page is a `WHERE (sort, id) </> (cursor)` seek rather than an
`OFFSET` scan. Cursors are opaque base64 tokens so clients never construct them
by hand and the server can evolve the encoding.

Sorting is restricted to non-null, monotonic columns (`created_at`,
`updated_at`, or the events `seq`) with `id` as a stable tiebreaker, which keeps
the keyset predicate correct and unambiguous.
"""
from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any, Sequence

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(sort_value: Any, id_value: Any) -> str:
    if isinstance(sort_value, datetime):
        sort_repr = {"t": "dt", "v": sort_value.isoformat()}
    else:
        sort_repr = {"t": "raw", "v": sort_value}
    raw = json.dumps({"s": sort_repr, "i": id_value}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[Any, Any]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        sort_repr = data["s"]
        value = datetime.fromisoformat(sort_repr["v"]) if sort_repr["t"] == "dt" else sort_repr["v"]
        return value, data["i"]
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def keyset_page(
    session: Session,
    stmt: Select,
    *,
    model: Any,
    sort_field: str,
    order: str,
    cursor: str | None,
    limit: int,
    allowed_sort_fields: Sequence[str],
) -> tuple[list[Any], str | None]:
    """Return one page of ORM rows plus the next cursor (None if exhausted)."""
    if sort_field not in allowed_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported sort '{sort_field}'. Allowed: {', '.join(allowed_sort_fields)}",
        )
    descending = order.lower() != "asc"
    sort_col = getattr(model, sort_field)
    id_col = getattr(model, "id")
    page_size = clamp_limit(limit)

    if cursor:
        sort_value, id_value = decode_cursor(cursor)
        if descending:
            stmt = stmt.where(
                or_(sort_col < sort_value, and_(sort_col == sort_value, id_col < id_value))
            )
        else:
            stmt = stmt.where(
                or_(sort_col > sort_value, and_(sort_col == sort_value, id_col > id_value))
            )

    if descending:
        stmt = stmt.order_by(sort_col.desc(), id_col.desc())
    else:
        stmt = stmt.order_by(sort_col.asc(), id_col.asc())

    rows = list(session.execute(stmt.limit(page_size + 1)).scalars())
    next_cursor: str | None = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        last = rows[-1]
        next_cursor = encode_cursor(getattr(last, sort_field), getattr(last, "id"))
    return rows, next_cursor


def page_response(items: list[dict[str, Any]], next_cursor: str | None, limit: int) -> dict[str, Any]:
    return {
        "items": items,
        "nextCursor": next_cursor,
        "hasMore": next_cursor is not None,
        "limit": clamp_limit(limit),
    }
