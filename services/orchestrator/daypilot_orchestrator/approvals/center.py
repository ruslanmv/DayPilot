"""Central Approval Center (batch B11).

One queue governs every sensitive action — email sends, calendar writes, repo
writes/PRs, file generation, persona enablement. Each item shows a
human-readable summary, risk, the policy that triggered it, and a decision with
a reason; every decision is audited. Approvals are the single choke point:
the model may propose, but the platform decides.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import Approval, AuditLog, Event

# Minimum role required to decide an approval, by the resource it governs.
DECISION_POLICY = {
    "coding_run": "operator",     # repo writes are high-impact
    "email_draft": "reviewer",
    "calendar_event": "reviewer",
    "document_output": "reviewer",
    "persona": "owner",           # persona enablement is owner-only
}
DEFAULT_DECISION_ROLE = "reviewer"


class ApprovalDecisionError(ValueError):
    pass


def required_role(resource_type: str | None) -> str:
    return DECISION_POLICY.get(resource_type or "", DEFAULT_DECISION_ROLE)


def decide(
    session: Session,
    approval_id: str,
    decision: str,
    reviewer: str = "local-owner",
    reason: str | None = None,
) -> dict[str, Any]:
    approval = session.get(Approval, approval_id)
    if approval is None:
        raise KeyError(approval_id)
    if decision not in {"approve", "reject"}:
        raise ApprovalDecisionError(f"Unknown decision '{decision}'")
    if approval.status != "pending":
        raise ApprovalDecisionError(f"Approval already {approval.status}")

    approval.status = "approved" if decision == "approve" else "rejected"
    approval.reason = reason
    approval.decided_at = datetime.utcnow()

    session.add(AuditLog(
        event_type="approval.decided",
        risk=approval.risk,
        decision=approval.status,
        payload_json={
            "approvalId": approval.id, "action": approval.action,
            "resourceType": approval.resource_type, "resourceId": approval.resource_id,
            "reviewer": reviewer, "reason": reason,
        },
    ))
    session.add(Event(
        workspace_id=approval.workspace_id, type="agent.state_changed",
        payload_json={"kind": "approval", "approvalId": approval.id, "status": approval.status},
    ))
    session.flush()
    return {
        "id": approval.id,
        "status": approval.status,
        "action": approval.action,
        "resourceType": approval.resource_type,
        "resourceId": approval.resource_id,
        "decidedAt": approval.decided_at.isoformat(),
        "reason": reason,
    }


def summary(session: Session, workspace_id: str = "default") -> dict[str, Any]:
    rows = session.execute(
        select(Approval.status, func.count()).where(
            Approval.workspace_id == workspace_id
        ).group_by(Approval.status)
    ).all()
    by_status = {status: int(count) for status, count in rows}
    risk_rows = session.execute(
        select(Approval.risk, func.count()).where(
            Approval.workspace_id == workspace_id, Approval.status == "pending"
        ).group_by(Approval.risk)
    ).all()
    return {
        "pending": by_status.get("pending", 0),
        "approved": by_status.get("approved", 0),
        "rejected": by_status.get("rejected", 0),
        "pendingByRisk": {risk: int(count) for risk, count in risk_rows},
    }


def export_audit(session: Session, fmt: str = "jsonl", limit: int = 5000) -> tuple[str, str]:
    """Export audit records. Returns (content, media_type)."""
    rows = list(
        session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        ).scalars()
    )
    records = [
        {
            "id": r.id,
            "eventType": r.event_type,
            "risk": r.risk,
            "decision": r.decision,
            "payload": r.payload_json,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "eventType", "risk", "decision", "createdAt", "payload"])
        for rec in records:
            writer.writerow([rec["id"], rec["eventType"], rec["risk"], rec["decision"],
                             rec["createdAt"], json.dumps(rec["payload"])])
        return buffer.getvalue(), "text/csv"
    return "\n".join(json.dumps(rec) for rec in records), "application/x-ndjson"
