# Assistant orchestrator

The assistant's intent routing and capability dispatch live in the backend
(`services/orchestrator/daypilot_orchestrator/assistant/`). The browser is a thin
client: it posts the user's message and renders the typed result. The backend is
the single authority for what the assistant does, and it holds a durable audit
trail of every turn.

## Why backend-owned

An earlier build classified intents and called planner/integration/approval
endpoints from the browser. That put authority in an untrusted place and made the
behavior client-specific. Moving it server-side makes routing deterministic,
identical for every client (web, mobile, future desktop), testable, and auditable
— and it lets the governance guarantees below be **structural** rather than
UI conventions.

## API

Base path `/v1/assistant`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/turn` | Run one turn. Body: `{ message, workspaceId, sessionId? }`. Returns the deterministic reply + optional action + tools used + `limited`. |
| `GET` | `/tools` | The registered tools and their risk classes (transparency). |
| `GET` | `/runs/{id}` | Inspect a run. |
| `GET` | `/runs/{id}/events` | The ordered event trail for a run. |
| `POST` | `/runs/{id}/cancel` | Cancel a running turn (idempotent for finished runs). |

A turn response:

```jsonc
{
  "runId": "…",
  "intent": "send_email",
  "state": "succeeded",
  "reply": "I've prepared that email as a draft and opened an approval — …",
  "action": { "kind": "openApprovals" },
  "tools": [ { "capability": "email.send", "risk": "approval_required" } ],
  "limited": false,
  "approvalId": "…"        // present for prepared write intents
}
```

## Intents

Classified server-side (`intents.py`); word-ish matching avoids matching short
tokens inside other words.

- **Read / local:** `date`, `plan`, `replan`, `integrations`, `email`,
  `approvals`, `new_project`.
- **Write (prepared, never performed):** `send_email`, `schedule`, `coding`.
- `unknown` → a short, honest scope statement (never a fabricated answer).

## Tool risk registry

Every capability is registered with a risk class (`tools.py`). The orchestrator
consults the registry before dispatching, so the authority model is centralized.

| Risk class | Meaning | Assistant may… |
|---|---|---|
| `READ_ONLY` | Reads state only | invoke directly |
| `CONTROLLED_LOCAL_WRITE` | Writes only local DayPilot state (draft plan, task) | invoke directly |
| `APPROVAL_REQUIRED` | Would mutate an external system or send | **prepare only** — open an approval; never perform |
| `BLOCKED` | Destructive / egress forbidden by default | never available |

`email.send`, `calendar.write`, and `coding.run` are `APPROVAL_REQUIRED`;
`mailbox.delete` / `mailbox.expunge` are `BLOCKED`.

## Governance guarantees (structural, not conventional)

- **Deterministic authority.** `guard.assert_not_directly_performed()` makes it
  impossible for the orchestrator to directly perform an `APPROVAL_REQUIRED` or
  `BLOCKED` capability. Write intents flow through the prepare-approval path only.
- **Approval / job linkage.** A prepared write opens a pending `Approval`. For
  `coding`, a queued `Job` is created and linked to the approval
  (`resource_type="coding_job"`, `resource_id=<jobId>`) — nothing runs until the
  approval is granted.
- **No approval bypass.** Requests like "send it without asking" are recognized
  (`guard.wants_to_bypass_approval`) and explicitly refused — the approval gate is
  never skipped.
- **Prompt-injection scanning.** Each message is scanned
  (`security/injection_guard.py`). A flagged turn emits a `guard.injection_flagged`
  event, notes that embedded instructions were ignored, and still cannot escalate.
- **Never direct egress.** The assistant never sends email or calls a
  provider/MCP server directly; it only orchestrates reads and prepares approvals.

## Limited mode

When no AI provider connection is `connected`, the turn runs in **limited mode**
(`limited: true`). Deterministic answers (date, readiness, status, approvals,
prepared writes) still work; plan/replan note that DayPilot's built-in planner is
used without an AI narrative. The assistant never pretends a provider is
connected when it isn't.

## Audit trail

Each turn writes an `AssistantRun` and a sequence of `AssistantRunEvent`s
(`run.started`, `intent.classified`, `guard.injection_flagged?`,
`approval.prepared?`, `run.succeeded` / `run.failed` / `run.cancelled`). Runs are
scoped per workspace and never leak across workspaces.
