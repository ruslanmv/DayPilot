# Architecture

DayPilot separates experience, control, execution, intelligence, local data, and observability.

```text
Operator UI → API Gateway → Orchestrator → MCP Host → Tools / Knowledge / Models
                              ↓
                         Approval Queue
                              ↓
                         Observability
```

The HomePilot bridge lives inside the MCP host because `.hpersona` import is treated as a governed tool operation.

## Backend-owned state (the browser never fabricates it)

An early build inferred connection state in the browser (provider/mailbox status
from `localStorage`, client-side assistant routing). The production architecture
makes the **backend the single source of truth** for identity, connections, and
what the assistant does. The browser sends intent and renders results; it never
invents a connection or performs a privileged action.

| Concern | Owner | Persistence | Secrets |
|---|---|---|---|
| **Identity & sessions** | API gateway (`identity.py`) | `users`, `workspaces`, `workspace_memberships`, `auth_sessions`, `auth_events` | scrypt password hashes; SHA-256 session-token hashes; HttpOnly cookie + CSRF double-submit |
| **AI providers** | Gateway (`providers_platform.py`) | `provider_connections` | keys/tokens in the credential store by `secret_reference` |
| **Mailboxes** | Gateway (`mail_setup.py`) | `mailbox_connections` | IMAP/OAuth secrets in the credential store by `secret_reference` |
| **Assistant** | Orchestrator (`assistant/`) | `assistant_runs`, `assistant_run_events` | none — orchestration only |

The corresponding schema is delivered by Alembic migrations `0008`–`0011`.

## The assistant orchestrator

Intent routing and capability dispatch are **backend-owned** (`daypilot_orchestrator/assistant/`).
The browser's `assistant.ts` is a thin client over `POST /v1/assistant/turn`; it
sends the user's message and renders the typed result (a deterministic reply plus
an optional UI action).

```text
message → /v1/assistant/turn
            classify_intent (server-side authority)
            guard.scan_message (prompt-injection scan)
            dispatch → real services (planner / integrations / mailbox / approvals)
                       read-only + controlled-local-write run directly
                       approval-required are PREPARED (open an Approval), never performed
            → AssistantRun (+ AssistantRunEvent audit trail)
```

Each turn is a durable `AssistantRun` with an event trail, inspectable via
`GET /v1/assistant/runs/{id}` and `/events`, cancellable via `/cancel`. See
[assistant-orchestrator.md](./assistant-orchestrator.md) for the full contract,
the tool risk registry, and the governance guarantees.

## Non-destructive by default

Reads, classification, and local drafts are always safe. Anything that mutates an
external system or sends is approval-gated and audited — enforced in the
backend, not the UI. The assistant never sends email or calls a provider/MCP
server directly: it prepares an approval (and, for coding, a gated job) and the
action only runs after explicit human approval. See
[security.md](./security.md).

## Implementation order (architecture review)

The backend-owned model was delivered in batches:

- **Batch 0** — transport + truthful state (Vite/API proxy, content-type-safe client, remove fabricated status).
- **Batch 1** — identity & login (accounts, workspaces, memberships, sessions, enterprise login).
- **Batch 2** — provider connection platform (persistent metadata, durable secrets, local discovery, cloud login).
- **Batch 3** — mail onboarding (workspace mailbox model, shared setup wizard, non-destructive IMAP/SMTP probe).
- **Batch 4** — assistant orchestrator (turn/run/event APIs, typed read tools, planner/integration/approval wiring).
- **Batch 5** — specialized writes + governance (prepared approvals, approval/job linkage, injection + tool-validation controls).
- **Batch 6** — hardening + release (workspace-isolation, secret-persistence, and migration round-trip verification).
