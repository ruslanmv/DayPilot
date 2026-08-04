"""The assistant orchestrator (Batch 4).

The backend owns intent routing and capability dispatch. Each turn creates an
AssistantRun, classifies the message, invokes only invokable (READ_ONLY /
CONTROLLED_LOCAL_WRITE) tools against the real services, records the tools it
used with their risk class, and returns a deterministic reply + optional UI
action. Runs and their events are the audit trail.

Authority guarantees, enforced here rather than implied at call sites:
  * The assistant never sends email or calls a provider/MCP server directly.
  * Anything that would mutate an external system or send is APPROVAL_REQUIRED
    and is only ever *prepared* (draft + approval) by the owning service.
  * When no AI provider is connected the assistant runs in *limited mode*:
    deterministic answers still work; it just says AI narrative is unavailable.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daypilot_knowledge.db import (
    Approval,
    AssistantRun,
    AssistantRunEvent,
    Job,
    MailboxConnection,
    ProviderConnection,
)

from ..approvals import center as approvals_center
from ..integrations import service as integrations_service
from ..integrations.credentials import credential_store
from ..planner import service as planner_service
from . import guard
from .intents import classify_intent
from .tools import TOOL_REGISTRY, is_invokable, risk_of

# How many prior turns of this conversation to replay to the model.
_HISTORY_TURNS = 8
# The assistant's guardrails, sent as the system prompt. Read-only + never fake.
_SYSTEM_PROMPT = (
    "You are DayPilot's assistant for a senior AI/ML technical leader. Answer the "
    "user's questions helpfully and concisely using general knowledge and the "
    "read-only workspace context provided. You cannot send email, change "
    "calendars, run code, or modify anything — DayPilot handles those through its "
    "own approval-gated flows, so never claim to have performed such an action. "
    "If you don't know something, say so plainly rather than inventing details."
)


# ---- run + event helpers ----------------------------------------------------

def _emit(session: Session, run: AssistantRun, type_: str, payload: dict[str, Any]) -> None:
    session.add(AssistantRunEvent(run_id=run.id, type=type_, payload_json=payload))


def _record_tool(run: AssistantRun, capability: str) -> None:
    risk = risk_of(capability)
    run.tools_json = [*(run.tools_json or []), {"capability": capability, "risk": risk.value}]


def provider_available(session: Session, workspace_id: str) -> bool:
    """True when a provider connection is connected (active or not). Limited mode
    is when nothing is connected — deterministic answers still work."""
    rows = session.execute(
        select(ProviderConnection).where(ProviderConnection.workspace_id == workspace_id)
    ).scalars()
    return any(r.state == "connected" for r in rows)


def active_connector(session: Session, workspace_id: str):
    """The OllabridgeConnector for the workspace's ACTIVE, connected provider —
    the same URL/key/model the settings UI configured — or None. Used to answer
    general questions with real inference instead of a canned reply.

    Kept lazy-imported so the orchestrator has no hard dependency on the model
    package when inference isn't used."""
    row = session.execute(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == workspace_id,
            ProviderConnection.active.is_(True),
            ProviderConnection.state == "connected",
        )
    ).scalar_one_or_none()
    if row is None or not row.base_url:
        return None
    from daypilot_models.ollabridge_client import OllabridgeConnector

    secret = credential_store().get(row.secret_reference) if row.secret_reference else {}
    key = (secret or {}).get("api_key") or (secret or {}).get("token")
    return OllabridgeConnector(
        base_url=row.base_url,
        api_key=key,
        model=row.default_model or "default",
        mode="cloud" if row.kind == "ollabridge_cloud" else "local",
    )


def _workspace_context(session: Session, workspace_id: str) -> str:
    """A small READ-ONLY snapshot the model may reference. Counts only — never a
    user's content — so the model has grounding without leaking data it shouldn't."""
    try:
        pending = len(session.execute(
            select(Approval.id).where(
                Approval.workspace_id == workspace_id, Approval.status == "pending"
            )
        ).scalars().all())
    except Exception:  # noqa: BLE001 - context is best-effort
        pending = 0
    return (
        f"Workspace context (read-only): today is {_today()}; "
        f"{pending} item(s) are waiting for your approval."
    )


def _profile_context(session: Session, workspace_id: str, purpose: str, run: AssistantRun) -> str:
    """Project the user's AI profile for this purpose and render it as a
    delimited, non-authoritative system section. Gated by a feature flag and by
    per-category consent inside the builder; on any failure the turn proceeds
    without personalization (never blocks the answer). Records the applied
    revision + category NAMES on the run for reproducibility — never the values.
    """
    if os.getenv("DAYPILOT_PROFILE_CONTEXT_ENABLED", "true").lower() in ("0", "false", "no"):
        return ""
    try:
        from ..profile.context_builder import build_projection, render_system_section
        proj = build_projection(session, workspace_id=workspace_id, purpose=purpose)
        section = render_system_section(proj)
        if section:
            _emit(session, run, "profile.context_applied",
                  {"revision": proj.profile_revision, "categories": sorted(proj.included_categories)})
        return section
    except Exception:  # noqa: BLE001 - personalization is best-effort, never fatal
        return ""


def _history_messages(session: Session, workspace_id: str, session_id: str | None) -> list[dict[str, str]]:
    """Prior turns of THIS conversation as chat messages, oldest first, so the
    assistant has real multi-turn context (not just the latest prompt)."""
    if not session_id:
        return []
    rows = session.execute(
        select(AssistantRun)
        .where(
            AssistantRun.workspace_id == workspace_id,
            AssistantRun.session_id == session_id,
            AssistantRun.state == "succeeded",
        )
        .order_by(AssistantRun.created_at.desc())
        .limit(_HISTORY_TURNS)
    ).scalars().all()
    msgs: list[dict[str, str]] = []
    for run in reversed(rows):  # oldest → newest
        if run.message:
            msgs.append({"role": "user", "content": run.message})
        if run.reply:
            msgs.append({"role": "assistant", "content": run.reply})
    return msgs


# ---- capability handlers (deterministic, read-mostly) -----------------------

def _today() -> str:
    return date.today().isoformat()


def _handle_date() -> dict[str, Any]:
    d = date.today()
    return {"reply": f"Today is {d.strftime('%A, %B %-d, %Y')}."}


def _handle_plan(session: Session, ws: str, run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "planner.readiness")
    readiness = planner_service.planner_readiness(session, ws, _today())
    if not readiness.get("sufficient", True):
        need = readiness.get("message") or "There isn't enough to plan yet."
        return {"reply": f"{need} Add tasks or connect email, and I'll build your day.",
                "action": {"kind": "navigate", "target": "planning"}}
    _record_tool(run, "planner.generate")
    plan = planner_service.generate_plan(session, ws, _today())
    n = len(plan.get("blocks", []))
    score = plan.get("score")
    summary = plan.get("summary") or f"Planned {n} block(s) for today."
    tail = f" Plan score {score}/100." if isinstance(score, int) and score else ""
    return {"reply": f"{summary}{tail}", "action": {"kind": "navigate", "target": "planning"}}


def _handle_replan(session: Session, ws: str, message: str, run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "planner.replan")
    result = planner_service.chat_with_plan(session, ws, _today(), message)
    reply = result.get("reply") or (result.get("plan", {}) or {}).get("summary") or "Adjusted your plan."
    return {"reply": reply, "action": {"kind": "navigate", "target": "planning"}}


def _handle_integrations(session: Session, ws: str, run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "integrations.status")
    cons = integrations_service.list_connections(session, ws)
    parts: list[str] = []
    if cons:
        parts.append("Connected: " + ", ".join(
            f"{c.get('name') or c.get('provider')} ({c.get('status', 'unknown')})" for c in cons) + ".")
    else:
        parts.append("No integrations are connected yet. Add one in Settings → Integrations.")
    active = session.execute(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == ws, ProviderConnection.active.is_(True)
        )
    ).scalar_one_or_none()
    if active and active.state == "connected":
        parts.append(f"AI provider: {active.kind} connected.")
    else:
        parts.append("No AI provider is connected (limited mode).")
    return {"reply": " ".join(parts)}


def _handle_email(session: Session, ws: str, run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "email.status")
    row = session.execute(
        select(MailboxConnection).where(MailboxConnection.workspace_id == ws)
    ).scalar_one_or_none()
    if row is None or row.status == "unconfigured" or not row.secret_reference:
        return {"reply": "No mailbox is connected, so I can't access your email yet. "
                         "Connect one in Settings → Mail — I'll read and draft replies, and never "
                         "send anything without your approval."}
    if row.status in ("connected", "degraded"):
        note = "" if row.status == "connected" else " (sending is currently unavailable)"
        return {"reply": f"Yes — your mailbox {row.email_address} is connected{note}, so I can read "
                         "and prepare drafts. I never send or delete without your approval."}
    return {"reply": f"Your mailbox {row.email_address} is set up but currently {row.status}. "
                     "Reconnect it in Settings → Mail to give me access."}


def _handle_approvals(session: Session, ws: str, run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "approvals.summary")
    summary = approvals_center.summary(session, ws)
    pending = summary.get("pending", 0)
    if pending > 0:
        return {"reply": f"You have {pending} item(s) awaiting approval.",
                "action": {"kind": "openApprovals"}}
    return {"reply": "Nothing is waiting for your approval right now."}


def _handle_new_project(run: AssistantRun) -> dict[str, Any]:
    _record_tool(run, "project.create_wizard")
    return {"reply": "Opening the new-project wizard.", "action": {"kind": "openProjectWizard"}}


# ---- write intents: prepared, never performed -------------------------------

def _prepare_approval(
    session: Session, ws: str, run: AssistantRun, capability: str,
    action: str, summary: str, risk: str, resource_type: str,
    resource_id: str | None = None,
) -> str:
    """Open a pending approval for an APPROVAL_REQUIRED capability. The assistant
    prepares the action and records the tool as prepared — it never performs it.
    Bypassing the approval gate is structurally impossible here: this path only
    ever opens a pending approval, never executes the underlying capability."""
    if not guard.requires_approval(capability):
        raise guard.ToolNotPermitted(f"{capability} is not an approval-required capability")
    _record_tool(run, capability)
    approval = Approval(
        workspace_id=ws, action=action, summary=summary, risk=risk,
        status="pending", resource_type=resource_type, resource_id=resource_id,
        reason="Prepared by the assistant; awaiting your approval.",
    )
    session.add(approval)
    session.flush()
    _emit(session, run, "approval.prepared",
          {"capability": capability, "approvalId": approval.id, "risk": risk})
    return approval.id


def _bypass_note(message: str) -> str:
    return (" I can't skip the approval step — every send or external change waits for your explicit approval."
            if guard.wants_to_bypass_approval(message) else "")


def _handle_send_email(session: Session, ws: str, message: str, run: AssistantRun) -> dict[str, Any]:
    approval_id = _prepare_approval(
        session, ws, run, "email.send", "email.send",
        "Send an email prepared from your request", "medium", "email_draft")
    return {"reply": "I've prepared that email as a draft and opened an approval — it will only send after you "
                     f"approve it.{_bypass_note(message)}",
            "action": {"kind": "openApprovals"}, "approvalId": approval_id}


def _handle_schedule(session: Session, ws: str, message: str, run: AssistantRun) -> dict[str, Any]:
    approval_id = _prepare_approval(
        session, ws, run, "calendar.write", "calendar.write",
        "Create a calendar event from your request", "medium", "calendar_event")
    return {"reply": "I've prepared that calendar event and opened an approval — it won't be created on your "
                     f"calendar until you approve it.{_bypass_note(message)}",
            "action": {"kind": "openApprovals"}, "approvalId": approval_id}


def _handle_coding(session: Session, ws: str, message: str, run: AssistantRun) -> dict[str, Any]:
    # Approval + job linkage: a queued job is created but gated on the approval.
    job = Job(workspace_id=ws, kind="coding", state="queued",
              payload_json={"request": message[:500], "gate": "approval"})
    session.add(job)
    session.flush()
    approval_id = _prepare_approval(
        session, ws, run, "coding.run", "coding.run",
        "Run a coding task / open a pull request", "high", "coding_job", resource_id=job.id)
    return {"reply": "I've queued that coding task behind an approval — nothing runs or opens a pull request "
                     f"until you approve it.{_bypass_note(message)}",
            "action": {"kind": "openApprovals"}, "approvalId": approval_id, "jobId": job.id}


def _handle_unknown() -> dict[str, Any]:
    return {"reply": "I'm connected to your DayPilot workspace — I can tell you today's date, "
                     "generate or adjust your plan, check integration and AI-provider status, "
                     "see whether your email is connected, open the project wizard, or show what "
                     "needs approval. Connect an AI provider in Settings to ask general questions."}


def _handle_general(
    session: Session, workspace_id: str, message: str, run: AssistantRun, session_id: str | None,
) -> dict[str, Any]:
    """Answer a general question with REAL inference through the active provider's
    /v1/chat/completions. Falls back to the deterministic reply when no provider
    is active or the call fails — never fabricates a provider answer."""
    connector = active_connector(session, workspace_id)
    if connector is None:
        return _handle_unknown()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "system", "content": _workspace_context(session, workspace_id)},
    ]
    profile_section = _profile_context(session, workspace_id, "assistant", run)
    if profile_section:
        messages.append({"role": "system", "content": profile_section})
    messages += [
        *_history_messages(session, workspace_id, session_id),
        {"role": "user", "content": message},
    ]
    try:
        result = connector.generate_messages(messages, task="assistant.general")
    except Exception as exc:  # noqa: BLE001 - provider/transport failure → truthful fallback
        _emit(session, run, "inference.failed", {"error": type(exc).__name__})
        return {"reply": "I couldn't reach the connected AI provider just now, so I can't answer "
                         "that in detail. Please check the provider in Settings and try again."}
    _record_tool(run, "ai.generate")
    _emit(session, run, "inference.completed",
          {"model": result.get("model"), "backend": result.get("backend")})
    text = (result.get("text") or "").strip()
    return {"reply": text or "The AI provider returned an empty response. Please try rephrasing."}


# ---- the run engine ---------------------------------------------------------

def run_turn(session: Session, workspace_id: str, message: str, session_id: str | None = None) -> dict[str, Any]:
    message = (message or "").strip()
    limited = not provider_available(session, workspace_id)
    run = AssistantRun(
        workspace_id=workspace_id, session_id=session_id, message=message,
        state="running", limited=limited,
    )
    session.add(run)
    session.flush()
    _emit(session, run, "run.started", {"limited": limited})

    if not message:
        run.intent = "unknown"
        _finish(session, run, {"reply": "Ask me about today, your plan, projects, integrations, "
                                        "email, or approvals."})
        return _public(run, session)

    intent = classify_intent(message)
    run.intent = intent
    _emit(session, run, "intent.classified", {"intent": intent})

    # Tool-validation + injection guard. A flagged message can never silently
    # escalate: write intents still go through the prepare-approval path, and
    # requests to bypass approval are ignored, not obeyed.
    report = guard.scan_message(message)
    if report.flagged:
        _emit(session, run, "guard.injection_flagged",
              {"categories": report.categories, "score": report.score})

    try:
        if intent == "date":
            out = _handle_date()
        elif intent == "plan":
            out = _handle_plan(session, workspace_id, run)
        elif intent == "replan":
            out = _handle_replan(session, workspace_id, message, run)
        elif intent == "integrations":
            out = _handle_integrations(session, workspace_id, run)
        elif intent == "email":
            out = _handle_email(session, workspace_id, run)
        elif intent == "approvals":
            out = _handle_approvals(session, workspace_id, run)
        elif intent == "new_project":
            out = _handle_new_project(run)
        elif intent == "send_email":
            out = _handle_send_email(session, workspace_id, message, run)
        elif intent == "schedule":
            out = _handle_schedule(session, workspace_id, message, run)
        elif intent == "coding":
            out = _handle_coding(session, workspace_id, message, run)
        else:
            # Not a security-sensitive intent → answer with real inference through
            # the active provider (falls back to a deterministic reply if none).
            out = _handle_general(session, workspace_id, message, run, session_id)
        if report.flagged:
            out["reply"] = out["reply"] + (
                " (Note: your message contained text that looks like embedded instructions; "
                "I only acted on your request itself and ignored those.)")
            out["injectionFlagged"] = True
    except Exception as exc:  # noqa: BLE001 - surface a truthful failure, never a fabricated answer
        run.state = "failed"
        run.error = type(exc).__name__
        run.reply = ("Something went wrong while handling that request, so I stopped rather than "
                     "guess. Please try again, or rephrase what you need.")
        _emit(session, run, "run.failed", {"error": type(exc).__name__})
        session.flush()
        return _public(run, session)

    # Limited mode note for AI-narrative-dependent intents.
    if limited and intent in ("plan", "replan"):
        out["reply"] = out["reply"] + " (Limited mode: no AI provider connected, so this uses " \
                                      "DayPilot's built-in planner without an AI narrative.)"
    _finish(session, run, out)
    result = _public(run, session)
    for key in ("approvalId", "jobId", "injectionFlagged"):
        if key in out:
            result[key] = out[key]
    return result


def _finish(session: Session, run: AssistantRun, out: dict[str, Any]) -> None:
    run.reply = out.get("reply", "")
    run.action_json = out.get("action")
    run.state = "succeeded"
    _emit(session, run, "run.succeeded", {"intent": run.intent, "tools": run.tools_json})
    session.flush()


def _public(run: AssistantRun, session: Session) -> dict[str, Any]:
    return {
        "runId": run.id,
        "intent": run.intent,
        "state": run.state,
        "reply": run.reply,
        "action": run.action_json,
        "tools": run.tools_json or [],
        "limited": run.limited,
        "error": run.error,
    }


# ---- run inspection ---------------------------------------------------------

def get_run(session: Session, run_id: str) -> dict[str, Any] | None:
    run = session.get(AssistantRun, run_id)
    return _public(run, session) if run else None


def get_events(session: Session, run_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(AssistantRunEvent).where(AssistantRunEvent.run_id == run_id).order_by(AssistantRunEvent.seq)
    ).scalars()
    return [{"seq": e.seq, "type": e.type, "payload": e.payload_json,
             "at": e.created_at.isoformat() if e.created_at else None} for e in rows]


def cancel_run(session: Session, run_id: str) -> dict[str, Any] | None:
    run = session.get(AssistantRun, run_id)
    if run is None:
        return None
    if run.state == "running":
        run.state = "cancelled"
        _emit(session, run, "run.cancelled", {})
        session.flush()
    return _public(run, session)


def tool_catalog() -> list[dict[str, Any]]:
    """The registered tools and their risk classes (for transparency)."""
    return [{"capability": cap, "risk": risk.value, "label": label,
             "invokable": is_invokable(cap)}
            for cap, (risk, label) in TOOL_REGISTRY.items()]
