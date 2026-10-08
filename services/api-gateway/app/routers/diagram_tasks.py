"""Send a map's open tasks to the DayPilot task list (batch C4). Explicit, idempotent, bounded."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Task

from ..db import get_session
from .diagrams import access, owned

router = APIRouter(prefix="/v1/diagrams", tags=["diagrams"])
MAX_ITEMS = 200


class Item(BaseModel):
    id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,100}$")
    title: str = Field(..., min_length=1, max_length=500)
    context: str = Field("", max_length=2000)
    due: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    priority: str = Field("medium", pattern="^(low|medium|high)$")


class PushIn(BaseModel):
    items: list[Item] = Field(..., min_length=1, max_length=MAX_ITEMS)
    projectId: str | None = Field(None, max_length=36)


def due_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@router.post("/{diagram_id}/tasks")
def push_tasks(
    diagram_id: str, body: PushIn, workspace: str = Depends(access), session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Create one task per item, once: re-sending the same topic updates nothing and creates nothing."""
    owned(session, diagram_id, workspace)
    sources = {f"dmind:{diagram_id}:{i.id}" for i in body.items}
    existing = set(
        session.execute(select(Task.source).where(Task.workspace_id == workspace, Task.source.in_(sources))).scalars()
    )
    created, skipped = 0, 0
    for item in body.items:
        source = f"dmind:{diagram_id}:{item.id}"
        if source in existing:
            skipped += 1
            continue
        existing.add(source)
        session.add(
            Task(
                workspace_id=workspace,
                title=re.sub(r"\s+", " ", item.title).strip(),
                owner="you",
                priority=item.priority,
                status="active",
                context=item.context or None,
                source=source,
                due_date=due_date(item.due),
                project_id=None,
            )
        )
        created += 1
    return {"created": created, "skipped": skipped}
