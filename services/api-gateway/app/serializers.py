"""ORM -> API dict serializers.

Output camelCase keys so payloads line up with the TypeScript domain contracts
in packages/shared-types without a translation layer on the client.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_task(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "workspaceId": t.workspace_id,
        "title": t.title,
        "owner": t.owner,
        "executor": t.executor,
        "priority": t.priority,
        "status": t.status,
        "day": t.day,
        "start": t.start_time,
        "end": t.end_time,
        "context": t.context,
        "source": t.source,
        "confidence": t.confidence,
        "risk": t.risk,
        "projectId": t.project_id,
        "dueDate": _iso(t.due_date),
        "skipImpact": t.skip_impact,
        "parallelAi": t.parallel_ai,
        "nextAction": t.next_action,
        "createdAt": _iso(t.created_at),
        "updatedAt": _iso(t.updated_at),
    }


def serialize_project(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "workspaceId": p.workspace_id,
        "name": p.name,
        "progress": p.progress,
        "status": p.status,
        "risk": p.risk,
        "aiActivity": p.ai_activity,
        "nextHumanAction": p.next_human_action,
        "continueAction": p.continue_action,
        "dueDate": _iso(p.due_date),
        "aiActions": p.ai_actions or [],
        "designerInput": p.designer_input or [],
        "recentSignals": p.recent_signals or [],
        "linkedSources": p.linked_sources or [],
        "yesterday": p.yesterday or [],
        "today": p.today or [],
        "blocked": p.blocked or [],
        "createdAt": _iso(p.created_at),
        "updatedAt": _iso(p.updated_at),
    }


def serialize_agent_run(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "workspaceId": a.workspace_id,
        "name": a.name,
        "agentKind": a.agent_kind,
        "currentWork": a.current_work,
        "state": a.state,
        "status": a.display_status,
        "provider": a.provider,
        "model": a.model,
        "mode": a.mode,
        "latencyMs": a.latency_ms,
        "detail": a.detail,
        "attempts": a.attempts,
        "lastError": a.last_error,
        "projectId": a.project_id,
        "createdAt": _iso(a.created_at),
        "updatedAt": _iso(a.updated_at),
    }


def serialize_document(d: Any) -> dict[str, Any]:
    return {
        "id": d.id,
        "title": d.title,
        "sourceUri": d.source_uri,
        "projectId": d.project_id,
        "status": d.status,
        "source": d.source,
        "ingestState": d.ingest_state,
        "sha256": d.sha256,
        "createdAt": _iso(d.created_at),
    }


def serialize_plan_block(b: Any) -> dict[str, Any]:
    return {
        "id": b.id,
        "taskId": b.task_id,
        "title": b.title,
        "start": b.start_time,
        "end": b.end_time,
        "owner": b.owner,
        "source": b.source,
        "status": b.status,
        "orderIndex": b.order_index,
    }


def serialize_day_plan(p: Any, blocks: list[Any] | None = None) -> dict[str, Any]:
    block_rows = blocks if blocks is not None else getattr(p, "blocks", [])
    ordered = sorted(block_rows, key=lambda b: b.order_index)
    return {
        "id": p.id,
        "workspaceId": p.workspace_id,
        "planDate": p.plan_date,
        "state": p.state,
        "summary": p.summary,
        "blocks": [serialize_plan_block(b) for b in ordered],
        "createdAt": _iso(p.created_at),
        "updatedAt": _iso(p.updated_at),
    }


def serialize_approval(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "workspaceId": a.workspace_id,
        "personaId": a.persona_id,
        "action": a.action,
        "summary": a.summary,
        "risk": a.risk,
        "status": a.status,
        "resourceType": a.resource_type,
        "resourceId": a.resource_id,
        "reason": a.reason,
        "createdAt": _iso(a.created_at),
        "decidedAt": _iso(a.decided_at),
    }


def serialize_event(e: Any) -> dict[str, Any]:
    return {
        "seq": e.seq,
        "id": e.id,
        "workspaceId": e.workspace_id,
        "type": e.type,
        "payload": e.payload_json or {},
        "createdAt": _iso(e.created_at),
    }
