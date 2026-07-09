from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response


class RunState(StrEnum):
    PLANNED = "PLANNED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


RISKY_WRITE_TOOLS = {
    "email.send",
    "calendar.create_event",
    "calendar.update_event",
    "mcp.write",
    "homepilot.import_hpersona",
}

RUNS_CREATED = Counter("daypilot_orchestrator_runs_created_total", "Agent runs planned")
RUN_STATE_TRANSITIONS = Counter(
    "daypilot_orchestrator_state_transitions_total", "Agent runtime state transitions", ["state"]
)
PLANNING_LATENCY = Histogram("daypilot_orchestrator_plan_seconds", "Planning latency")


@dataclass
class AgentRun:
    persona_id: str
    objective: str
    tools_requested: list[str] = field(default_factory=list)
    requires_approval: bool = True
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: RunState = RunState.PLANNED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approval_reason: str | None = None


class AgentRunRequest(BaseModel):
    persona_id: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    tools_requested: list[str] = Field(default_factory=list)
    allow_without_approval: bool = False


class AgentRunResponse(BaseModel):
    run_id: str
    persona_id: str
    objective: str
    tools_requested: list[str]
    requires_approval: bool
    state: RunState
    approval_reason: str | None
    created_at: str


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "block"]
    operator_id: str = "local-operator"
    reason: str | None = None


_RUN_STORE: dict[str, AgentRun] = {}


def _approval_required(tools_requested: list[str], allow_without_approval: bool) -> tuple[bool, str | None]:
    default_requires_approval = os.getenv("DAYPILOT_REQUIRE_APPROVAL", "true").lower() == "true"
    write_enabled = os.getenv("DAYPILOT_WRITE_ENABLED", "false").lower() == "true"
    risky_tools = sorted(set(tools_requested) & RISKY_WRITE_TOOLS)
    if risky_tools:
        return True, f"Risky write-capable tools requested: {', '.join(risky_tools)}"
    if not write_enabled and tools_requested:
        return True, "Write mode is disabled; operator approval required before tool execution."
    if default_requires_approval and not allow_without_approval:
        return True, "Global human-in-the-loop policy is enabled."
    return False, None


@PLANNING_LATENCY.time()
def plan_agent_run(
    persona_id: str,
    objective: str,
    tools_requested: list[str] | None = None,
    allow_without_approval: bool = False,
) -> AgentRun:
    """Create a governed DayPilot run plan and hold it before execution when policy requires it."""
    tools = tools_requested or []
    requires_approval, reason = _approval_required(tools, allow_without_approval)
    run = AgentRun(
        persona_id=persona_id,
        objective=objective,
        tools_requested=tools,
        requires_approval=requires_approval,
        approval_reason=reason,
        state=RunState.WAITING_APPROVAL if requires_approval else RunState.APPROVED,
    )
    _RUN_STORE[run.run_id] = run
    RUNS_CREATED.inc()
    RUN_STATE_TRANSITIONS.labels(state=run.state.value).inc()
    return run


def apply_approval(run_id: str, decision: ApprovalDecision) -> AgentRun:
    run = _RUN_STORE.get(run_id)
    if run is None:
        raise KeyError(run_id)
    if run.state not in {RunState.WAITING_APPROVAL, RunState.PLANNED}:
        raise ValueError(f"Run {run_id} is not waiting for approval; current state={run.state}")
    if decision.decision == "approve":
        run.state = RunState.APPROVED
        run.requires_approval = False
    else:
        run.state = RunState.BLOCKED
    run.approval_reason = decision.reason or run.approval_reason
    RUN_STATE_TRANSITIONS.labels(state=run.state.value).inc()
    return run


def serialize_run(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=run.run_id,
        persona_id=run.persona_id,
        objective=run.objective,
        tools_requested=run.tools_requested,
        requires_approval=run.requires_approval,
        state=run.state,
        approval_reason=run.approval_reason,
        created_at=run.created_at,
    )


app = FastAPI(title="DayPilot Orchestrator", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "daypilot-orchestrator", "runs": len(_RUN_STORE)}


@app.post("/v1/runs/plan", response_model=AgentRunResponse)
def create_run(request: AgentRunRequest) -> AgentRunResponse:
    return serialize_run(
        plan_agent_run(
            persona_id=request.persona_id,
            objective=request.objective,
            tools_requested=request.tools_requested,
            allow_without_approval=request.allow_without_approval,
        )
    )


@app.get("/v1/runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: str) -> AgentRunResponse:
    run = _RUN_STORE.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return serialize_run(run)


@app.post("/v1/runs/{run_id}/decision", response_model=AgentRunResponse)
def decide_run(run_id: str, decision: ApprovalDecision) -> AgentRunResponse:
    try:
        return serialize_run(apply_approval(run_id, decision))
    except KeyError:
        raise HTTPException(status_code=404, detail="Run not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
