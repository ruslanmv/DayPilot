"""Tests for the backend assistant orchestrator (Batch 4).

The backend owns intent routing and capability dispatch. These tests assert the
orchestrator classifies intents server-side, records the tools it used with an
honest risk class, keeps deterministic authority (never sends / never invokes
approval-required or blocked tools), reports limited mode when no provider is
connected, and exposes runs + events + cancel over the gateway.
"""
from __future__ import annotations

import json
import uuid

import httpx
from fastapi.testclient import TestClient

from app.main import app
from daypilot_knowledge.db import MailboxConnection, ProviderConnection, session_scope
from daypilot_orchestrator.assistant import orchestrator
from daypilot_orchestrator.assistant.intents import classify_intent
from daypilot_orchestrator.assistant.tools import ToolRisk, is_invokable, risk_of
from daypilot_orchestrator.integrations.credentials import credential_store

client = TestClient(app)


def _ws() -> str:
    return "asst-" + uuid.uuid4().hex[:8]


# --- real inference through the active provider (R2) -------------------------

def test_general_question_uses_active_provider_inference(monkeypatch):
    """An arbitrary question must reach the active provider's
    /v1/chat/completions (with its stored URL/key/model) and return the
    generated text — not the hard-coded 'unknown' fallback."""
    ws = _ws()
    ref = f"prov-secret-{ws}"
    credential_store().put(ref, {"api_key": "sk-test-123"})
    with session_scope() as s:
        s.add(ProviderConnection(
            workspace_id=ws, kind="local", state="connected", active=True,
            base_url="http://prov-host:11435/v1", default_model="llama-x",
            secret_reference=ref,
        ))

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        body = json.loads(request.content)
        seen["model"] = body["model"]
        seen["roles"] = [m["role"] for m in body["messages"]]
        return httpx.Response(200, json={
            "choices": [{"message": {"content":
                "Supervised learning uses labeled data; unsupervised finds structure in unlabeled data."}}],
            "usage": {},
        })

    transport = httpx.MockTransport(handler)
    from daypilot_models import ollabridge_client as oc
    real = oc.OllabridgeConnector

    def _factory(**kwargs):
        kwargs["transport"] = transport
        return real(**kwargs)

    # active_connector imports the class lazily from this module.
    monkeypatch.setattr(oc, "OllabridgeConnector", _factory)

    r = client.post("/v1/assistant/turn", json={
        "workspaceId": ws,
        "message": "Explain the difference between supervised and unsupervised learning.",
    })
    assert r.status_code == 200
    data = r.json()

    # /v1/chat/completions was called, with the provider's stored key + model.
    assert seen.get("path") == "/v1/chat/completions"
    assert seen.get("auth") == "Bearer sk-test-123"
    assert seen.get("model") == "llama-x"
    assert seen["roles"][0] == "system" and seen["roles"][-1] == "user"
    # The provider-generated text is returned, not the deterministic fallback.
    assert "unsupervised" in data["reply"].lower()
    assert "I don't have information" not in data["reply"]
    assert data["intent"] == "unknown"


def test_general_question_falls_back_without_active_provider():
    """With no active provider, an arbitrary question gets the deterministic
    reply (never a fabricated answer) — and no inference call is made."""
    ws = _ws()
    r = client.post("/v1/assistant/turn", json={
        "workspaceId": ws, "message": "Explain gradient descent in one paragraph.",
    })
    data = r.json()
    assert data["reply"].startswith("I'm connected to your DayPilot workspace")
    assert "Connect an AI provider" in data["reply"]


# --- intent classification is the server-side authority ---------------------

def test_intents_classify_expected():
    assert classify_intent("what is today?") == "date"
    assert classify_intent("plan my day") == "plan"
    assert classify_intent("move my 3pm and reschedule the review") == "replan"
    assert classify_intent("can you access my email?") == "email"
    assert classify_intent("are my integrations connected?") == "integrations"
    assert classify_intent("what needs approval?") == "approvals"
    assert classify_intent("start a project") == "new_project"
    assert classify_intent("what's the weather on mars") == "unknown"


# --- tool risk registry ------------------------------------------------------

def test_tool_risk_classes_and_invokability():
    assert risk_of("planner.read") == ToolRisk.READ_ONLY
    assert risk_of("planner.generate") == ToolRisk.CONTROLLED_LOCAL_WRITE
    assert risk_of("email.send") == ToolRisk.APPROVAL_REQUIRED
    assert risk_of("mailbox.delete") == ToolRisk.BLOCKED
    # Only read-only / controlled-local-write are directly invokable.
    assert is_invokable("planner.read") and is_invokable("planner.generate")
    assert not is_invokable("email.send") and not is_invokable("mailbox.delete")
    # Unknown capabilities default to blocked.
    assert risk_of("something.unknown") == ToolRisk.BLOCKED


# --- deterministic answers, honest tools ------------------------------------

def test_date_turn_is_deterministic_and_uses_no_write_tools():
    with session_scope() as s:
        out = orchestrator.run_turn(s, _ws(), "what is today's date?")
    assert out["intent"] == "date"
    assert out["state"] == "succeeded"
    assert "Today is" in out["reply"]
    # date is answered from the clock — no tools recorded that write.
    assert all(t["risk"] == ToolRisk.READ_ONLY.value for t in out["tools"])


def test_email_access_answer_reflects_real_connection():
    ws = _ws()
    with session_scope() as s:
        out = orchestrator.run_turn(s, ws, "can you access my email?")
    assert out["intent"] == "email"
    assert "No mailbox is connected" in out["reply"]
    assert out["tools"] == [{"capability": "email.status", "risk": "read_only"}]

    with session_scope() as s:
        s.add(MailboxConnection(workspace_id=ws, provider="imap", email_address="u@x.com",
                                status="connected", secret_reference=f"mailbox:{ws}"))
    with session_scope() as s:
        out = orchestrator.run_turn(s, ws, "do you have access to my inbox?")
    assert "connected" in out["reply"] and "u@x.com" in out["reply"]


def test_limited_mode_when_no_provider_connected():
    ws = _ws()
    with session_scope() as s:
        out = orchestrator.run_turn(s, ws, "are my integrations connected?")
    assert out["limited"] is True

    with session_scope() as s:
        s.add(ProviderConnection(workspace_id=ws, kind="local", state="connected", active=True))
    with session_scope() as s:
        out = orchestrator.run_turn(s, ws, "are my integrations connected?")
    assert out["limited"] is False


# --- gateway endpoints: turn, runs, events, cancel --------------------------

def test_turn_endpoint_and_run_events():
    ws = _ws()
    resp = client.post("/v1/assistant/turn", json={"message": "what is today?", "workspaceId": ws})
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["runId"]
    assert data["intent"] == "date" and data["state"] == "succeeded"

    run = client.get(f"/v1/assistant/runs/{run_id}").json()
    assert run["runId"] == run_id

    events = client.get(f"/v1/assistant/runs/{run_id}/events").json()["events"]
    types = [e["type"] for e in events]
    assert "run.started" in types and "intent.classified" in types and "run.succeeded" in types


def test_unknown_run_returns_404():
    assert client.get("/v1/assistant/runs/does-not-exist").status_code == 404


def test_tools_endpoint_exposes_risk_classes():
    tools = client.get("/v1/assistant/tools").json()["tools"]
    risks = {t["risk"] for t in tools}
    assert {"read_only", "controlled_local_write", "approval_required", "blocked"} <= risks
    # An approval-required tool is present and marked non-invokable.
    send = next(t for t in tools if t["capability"] == "email.send")
    assert send["invokable"] is False


def test_cancel_endpoint_is_idempotent_for_finished_runs():
    ws = _ws()
    run_id = client.post("/v1/assistant/turn", json={"message": "hi", "workspaceId": ws}).json()["runId"]
    # The run already succeeded synchronously; cancel returns the run unchanged.
    out = client.post(f"/v1/assistant/runs/{run_id}/cancel").json()
    assert out["state"] in ("succeeded", "cancelled")
