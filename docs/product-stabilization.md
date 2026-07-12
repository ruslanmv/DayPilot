# Product stabilization: clean data, connected AI, live planning

This milestone turns the prototype-feeling experience into a production-style
local app: a single run command, a clean real-data default, an AI assistant
wired to real backend data, required AI-provider onboarding, live planning, and
persistent chat history.

## 1. One command runs everything

| Command | What it does |
|---|---|
| `make run` | Starts the **API gateway and the web UI together** (Ctrl+C stops both). Prints URLs; the gateway auto-selects a free port if the requested one is busy. |
| `make serve` | Frontend / dev web UI only. `make run-web` is a backwards-compatible alias. |
| `make run-api` | API gateway only, free-port selection via `scripts/find_free_port.py`. |
| `make run PORT=9000` | Single `PORT` knob; `API_PORT`/`WEB_PORT` derive from it. |

`make help` is pure-make (no `awk`), so it works on Windows/WSL, and `install-js`
no longer runs `corepack enable` (which fails with EACCES on WSL).

## 2. Clean, real-data by default (demo is opt-in)

The shell ships **empty and connected** — no fabricated tasks, projects,
documents, agents, or assistant chatter. Sample content is gated behind
`VITE_DAYPILOT_DEMO_MODE=true`, and when on a visible **Demo mode** badge sits
next to the brand. Everything reads its seed data from `demoData.ts`, the single
switch between "empty, real" and "demo". Calm empty states cover the Home
priority/plan/continue cards, the Planning timeline, and the mobile drawer.

## 3. AI-provider onboarding (required)

First-run onboarding opens with an **AI provider** step. Ollabridge runs locally
by default (no cloud login); Ollabridge Cloud is optional. A **Test connection**
button verifies the provider against `/v1/providers/health` before AI can be
marked ready. The step can be deferred into an explicit, labelled *limited mode*
but not silently skipped; the choice is persisted (`daypilot.ai_ready`,
`isAiReady()`), so AI surfaces present themselves honestly.

## 4. The assistant is connected, not canned

`assistant.ts` routes every question to real backend data instead of a fixed
menu:

- date/today → answered from the real clock,
- "today's plan" / "replan" → the multi-agent planner (`/v1/planner/...`),
- integration + provider status → `/v1/integrations`, `/v1/providers/health`,
- "what needs approval" → `/v1/approvals/summary`,
- "new project" → opens the wizard.

Unreachable backends are reported honestly (never fabricated); unrelated
questions get a short, truthful scope statement rather than the old generic
fallback. The assistant stays read-only and orchestration-only — every write
remains approval-gated on the backend, and it never calls a provider or sends
email directly.

## 5. Live planning

The Planning tab loads the **real, persisted** plan (`GET /v1/planner/plans/{date}`),
and the chat panel calls `/v1/planner/plans/{date}/chat` so a change request
replans on the backend graph and the timeline updates live from the persisted
result. Replan/Generate run the graph and persist into the existing
`DayPlan`/`PlanBlock` lifecycle. Demo mode keeps the offline simulation.

## 6. Persistent chat sessions

`ChatSession` / `ChatMessage` models (migration `0007`) back a ChatGPT/Claude
-style history exposed at `/v1/chat/sessions` (list, create, read-with-messages,
rename, delete, clear-messages, append-message). The Home AI panel offers new
conversation, resume across refresh, a history switcher, per-conversation
delete, and clear-current. Only conversation text is stored — never credentials
or provider keys.

## Trust posture (unchanged)

Additive and non-destructive; every write/send/destructive action stays
approval-gated; the AI never sends email or calls a provider/MCP server
directly; credentials never appear in the database, logs, prompts, or traces.
