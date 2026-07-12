"""Integration Gateway service (batch I0/I1).

The single entry point the rest of DayPilot uses to talk to external providers.
It persists connection metadata (never credentials), classifies each action, and
enforces the permission model:

    read              -> executed immediately
    write/destructive -> a durable Job is enqueued and an Approval is opened;
                         nothing runs until the Approval is granted.

Every step is audited and emitted on the event stream. This mirrors the coding
workflow's create -> review -> write governance, reusing the Approval Center and
the durable job queue rather than inventing new machinery.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, Event, IntegrationConnection, Job

from ..security.secrets import redact
from .credentials import credential_store
from .permissions import RISK_BY_KIND, Permission, resolve_permission
from .provider import CapabilityNotFound, IntegrationError
from .registry import available_providers, build_provider


class WriteNotApproved(PermissionError):
    """A pending integration action was performed before its approval was granted."""


class ActionBlocked(PermissionError):
    """The capability's effective permission is 'blocked'."""


def _emit(session: Session, workspace_id: str, event_type: str, payload: dict[str, Any]) -> None:
    session.add(Event(workspace_id=workspace_id, type=event_type, payload_json=payload))


def _audit(session: Session, event_type: str, risk: str, decision: str, payload: dict[str, Any]) -> None:
    # Payloads here carry only identifiers/capability names — never credentials.
    session.add(AuditLog(event_type=event_type, risk=risk, decision=decision, payload_json=payload))


def _serialize(conn: IntegrationConnection) -> dict[str, Any]:
    return {
        "id": conn.id,
        "workspaceId": conn.workspace_id,
        "provider": conn.provider,
        "status": conn.status,
        "authType": conn.auth_type,
        "capabilities": list(conn.capabilities or []),
        "detail": conn.detail,
        "lastActivityAt": conn.last_activity_at.isoformat() if conn.last_activity_at else None,
    }


# --- Connections ------------------------------------------------------------

def create_connection(
    session: Session,
    workspace_id: str,
    provider: str,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    """Connect a provider: validate credentials, store them outside the DB, and
    persist a connection record. Raises IntegrationError on auth failure."""
    prov = build_provider(provider)
    prov.connect(credentials)  # validates; raises IntegrationError on failure
    caps = prov.list_capabilities()
    health = prov.get_health()

    conn = IntegrationConnection(
        workspace_id=workspace_id,
        provider=provider,
        status=health.status.value,
        auth_type=prov.auth_type.value,
        capabilities=[c.id for c in caps],
        detail=redact(health.detail or ""),
    )
    session.add(conn)
    session.flush()
    credential_store().put(conn.id, {k: str(v) for k, v in credentials.items()})
    _audit(session, "integration.connect", "low", "recorded",
           {"connectionId": conn.id, "provider": provider, "capabilities": conn.capabilities})
    _emit(session, workspace_id, "integration.connected",
          {"connectionId": conn.id, "provider": provider, "status": conn.status})
    return _serialize(conn)


def list_connections(session: Session, workspace_id: str = "default") -> list[dict[str, Any]]:
    rows = session.execute(
        select(IntegrationConnection).where(IntegrationConnection.workspace_id == workspace_id)
    ).scalars()
    return [_serialize(c) for c in rows]


def available(workspace_id: str = "default") -> list[str]:
    """Registered providers available to connect (marketplace-free, curated)."""
    return available_providers()


def get_connection(session: Session, connection_id: str) -> dict[str, Any] | None:
    conn = session.get(IntegrationConnection, connection_id)
    return _serialize(conn) if conn else None


def capabilities(session: Session, connection_id: str) -> list[dict[str, Any]]:
    conn = _require(session, connection_id)
    prov = build_provider(conn.provider)
    overrides = conn.permissions_json or {}
    out = []
    for cap in prov.list_capabilities():
        perm = resolve_permission(cap.kind, overrides, cap.id)
        out.append({**cap.as_dict(), "permission": perm.value})
    return out


def refresh_health(session: Session, connection_id: str) -> dict[str, Any]:
    """Re-check a connection and persist the new status — the 'detect and
    display connection failure' path."""
    conn = _require(session, connection_id)
    prov = build_provider(conn.provider)
    try:
        prov.connect(credential_store().get(conn.id))
        health = prov.get_health()
        conn.status = health.status.value
        conn.detail = redact(health.detail or "")
    except IntegrationError as exc:
        conn.status = "error"
        conn.detail = redact(str(exc))
    conn.updated_at = datetime.utcnow()
    _emit(session, conn.workspace_id, "integration.health",
          {"connectionId": conn.id, "status": conn.status})
    session.flush()
    return _serialize(conn)


def disconnect_connection(session: Session, connection_id: str) -> dict[str, Any]:
    conn = _require(session, connection_id)
    workspace_id, provider = conn.workspace_id, conn.provider
    try:
        prov = build_provider(provider)
        prov.disconnect()
    except Exception:  # pragma: no cover - disconnect is best-effort
        pass
    credential_store().delete(conn.id)  # revoke stored credentials
    session.delete(conn)
    _audit(session, "integration.disconnect", "low", "recorded",
           {"connectionId": connection_id, "provider": provider})
    _emit(session, workspace_id, "integration.disconnected",
          {"connectionId": connection_id, "provider": provider})
    session.flush()
    return {"id": connection_id, "status": "disconnected"}


# --- Action execution -------------------------------------------------------

def execute_action(
    session: Session,
    connection_id: str,
    action: str,
    payload: Any = None,
) -> dict[str, Any]:
    """Reads run immediately; writes/destructive actions open an Approval and a
    durable Job and do NOT execute until approved."""
    conn = _require(session, connection_id)
    prov = build_provider(conn.provider)
    caps = {c.id: c for c in prov.list_capabilities()}
    if action not in caps:
        raise CapabilityNotFound(action)
    cap = caps[action]
    perm = resolve_permission(cap.kind, conn.permissions_json or {}, action)
    risk = RISK_BY_KIND.get(cap.kind, "medium")

    if perm is Permission.BLOCKED:
        _audit(session, "integration.blocked", risk, "blocked",
               {"connectionId": conn.id, "capability": action})
        raise ActionBlocked(action)

    if perm is Permission.ALLOWED:
        prov.connect(credential_store().get(conn.id))
        result = prov.execute(action, payload)
        conn.last_activity_at = datetime.utcnow()
        _audit(session, "integration.read.executed", risk, "executed",
               {"connectionId": conn.id, "capability": action})
        _emit(session, conn.workspace_id, "integration.action_executed",
              {"connectionId": conn.id, "capability": action, "kind": cap.kind.value})
        session.flush()
        return {"status": "executed", "capability": action, "result": result}

    # APPROVAL_REQUIRED — enqueue a durable job and open an approval.
    job = Job(
        workspace_id=conn.workspace_id,
        kind="integration.execute",
        state="blocked_on_approval",
        payload_json={"connectionId": conn.id, "action": action, "input": payload},
    )
    session.add(job)
    session.flush()
    approval = Approval(
        workspace_id=conn.workspace_id,
        action=f"{conn.provider}.{action}",
        summary=f"Execute {action} on {conn.provider}",
        risk=risk,
        status="pending",
        resource_type="integration_action",
        resource_id=job.id,
    )
    session.add(approval)
    _audit(session, "integration.write.requested", risk, "recorded",
           {"connectionId": conn.id, "capability": action, "jobId": job.id, "approvalId": approval.id})
    _emit(session, conn.workspace_id, "approval.requested",
          {"resourceType": "integration_action", "resourceId": job.id, "capability": action})
    session.flush()
    return {"status": "approval_required", "capability": action, "approvalId": approval.id, "jobId": job.id}


def perform_pending_action(session: Session, job_id: str) -> dict[str, Any]:
    """Execute a previously approved write. Fails unless the linked approval is
    granted — the platform, not the model, decides."""
    job = session.get(Job, job_id)
    if job is None or job.kind != "integration.execute":
        raise KeyError(job_id)
    approval = session.execute(
        select(Approval).where(
            Approval.resource_type == "integration_action",
            Approval.resource_id == job_id,
        )
    ).scalars().first()
    if approval is None or approval.status != "approved":
        raise WriteNotApproved(job_id)
    if job.state == "succeeded":
        return {"status": "executed", "jobId": job_id, "result": job.result_json.get("result")}

    conn = _require(session, job.payload_json["connectionId"])
    prov = build_provider(conn.provider)
    prov.connect(credential_store().get(conn.id))
    result = prov.execute(job.payload_json["action"], job.payload_json.get("input"))

    job.state = "succeeded"
    job.result_json = {"result": result}
    conn.last_activity_at = datetime.utcnow()
    _audit(session, "integration.write.executed", approval.risk, "executed",
           {"connectionId": conn.id, "capability": job.payload_json["action"], "jobId": job_id})
    _emit(session, conn.workspace_id, "integration.action_executed",
          {"connectionId": conn.id, "capability": job.payload_json["action"], "kind": "write"})
    session.flush()
    return {"status": "executed", "jobId": job_id, "result": result}


# --- Autonomous processing (worker path) ------------------------------------

def promote_approved_actions(session: Session) -> int:
    """Release gated integration jobs once their approval is decided: approved →
    queued (a worker will run it), rejected → cancelled. Decoupled from the
    Approval Center, so `decide` needs no integration-specific logic."""
    jobs = session.execute(
        select(Job).where(Job.kind == "integration.execute", Job.state == "blocked_on_approval")
    ).scalars().all()
    promoted = 0
    for job in jobs:
        approval = session.execute(
            select(Approval).where(
                Approval.resource_type == "integration_action",
                Approval.resource_id == job.id,
            )
        ).scalars().first()
        if approval is None:
            continue
        if approval.status == "approved":
            job.state = "queued"
            job.run_after = datetime.utcnow()
            promoted += 1
        elif approval.status == "rejected":
            job.state = "cancelled"
    session.flush()
    return promoted


def execute_job_payload(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Worker handler for a `integration.execute` job. The approval has already
    been granted (the job would not be queued otherwise); this performs the
    provider call and records the result."""
    conn = _require(session, payload["connectionId"])
    prov = build_provider(conn.provider)
    prov.connect(credential_store().get(conn.id))
    result = prov.execute(payload["action"], payload.get("input"))
    conn.last_activity_at = datetime.utcnow()
    _audit(session, "integration.write.executed", "medium", "executed",
           {"connectionId": conn.id, "capability": payload["action"]})
    _emit(session, conn.workspace_id, "integration.action_executed",
          {"connectionId": conn.id, "capability": payload["action"], "kind": "write"})
    return {"result": result}


def _require(session: Session, connection_id: str) -> IntegrationConnection:
    conn = session.get(IntegrationConnection, connection_id)
    if conn is None:
        raise KeyError(connection_id)
    return conn
