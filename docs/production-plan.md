# DayPilot Production Plan — Batch Roadmap

This is the executable production completion plan for DayPilot Enterprise. It converts every placeholder tracked in [`TODO.md`](../TODO.md) into an ordered, dependency-aware sequence of **batches**. Each batch is a self-contained unit of work sized so it can be generated and reviewed as one changeset — by a human, by GitPilot (the default coding bridge), or by Claude Code / Codex as optional executors — following the same batch discipline Matrix Designer uses for Design Bundles.

## 1. How to use this plan

- Execute batches in order within a track; tracks can run in parallel where the dependency graph allows.
- Every batch lists: **goal, dependencies, files to create or refactor, work items, acceptance criteria, and the TODO.md placeholders it closes**.
- A batch is done when its acceptance criteria pass and its TODO.md checkboxes can be ticked.
- No batch may violate the product safety rules: writes are approval-gated, originals are never overwritten, secrets never appear in logs or prompts.

### Product defaults locked in by this plan

| Concern | Default | Notes |
|---|---|---|
| Coding workflow bridge | **GitPilot** (retro-compatible by default) | `POST /api/v1/gitpilot/runs` A2A contract, Ask/Auto/Plan modes, controlled diffs, never self-approves. |
| Optional coding executors | Claude Code, Codex | Behind the same `CodingWorkflowAdapter` interface as GitPilot. |
| LLM provider layer | **Ollabridge** | One OpenAI-compatible URL + key; routes local Ollama, remote GPUs, and cloud accounts; health/latency/fallback surfaced in Settings. |
| Planner / design reviewer | **Matrix Designer** | Produces Design Bundles and batch roadmaps that feed the day plan; reviews UI/deck/document quality. |
| Inbox agent | **Email Sentinel** | Classifies, drafts, detects schedule impact; never sends without approval. |
| Design language | **HomePilot Family** | Shared token package, calm premium dark workspace, local-first iconography. |
| Target user | AI/ML Principal Engineer | Thousands of tasks, many repos, agents, documents, and approvals live at once. |
| Form factors | Desktop command center + phone companion | Tauri desktop, web PWA, mobile PWA with offline sync and push-ready approvals. |

## 2. Current state audit

The repository is a well-structured scaffold (~2,900 lines of app code) whose runtime behavior is still seeded/static:

| Area | Today | Key files |
|---|---|---|
| UI | Single 624-line portal component rendering seeded fixtures; sidebar footer is a text stub (`More: Inbox · GitPilot · Settings`) | `packages/ui-bridge/src/minimalPortal.tsx`, `spaceBridgeData.ts`, `space-bridge.css` |
| Web / mobile / desktop shells | 10-line `main.tsx` mounting the same portal; Tauri config only | `apps/operator-web`, `apps/mobile-pwa`, `apps/operator-desktop` |
| API gateway | Health, static briefing, persona preview/list, metrics — no domain APIs | `services/api-gateway/app/main.py` (75 lines) |
| Orchestrator | In-memory agent runtime sketch, no queue, no durability | `services/orchestrator/daypilot_orchestrator/agent_runtime.py` |
| MCP host | `.hpersona` bridge + static registry; no live tool execution | `services/mcp-host/daypilot_mcp_host/` |
| Knowledge service | Chunk models + pipeline stub; no parsers, no vector index | `services/knowledge-service/daypilot_knowledge/` |
| Model serving | Mock/Ollama/OpenAI connector stubs; no Ollabridge client, no health/fallback | `services/model-serving/daypilot_models/` |
| Data | Alembic `0001_initial_core_schema` for users/personas/calendars/inboxes/documents/chunks/audit; no tasks/projects/agent-runs tables | `alembic/versions/0001_initial_core_schema.py` |
| Contracts | Good TS domain types but frontend-only; no OpenAPI parity | `packages/shared-types/src/index.ts` |
| Infra | Compose + K8s + Terraform skeletons; Prometheus config; CI workflow stubs | `infra/`, `.github/workflows/` |

Everything in section 10 of `TODO.md` ("Current Placeholder Inventory") is confirmed by this audit.

## 3. Batch roadmap overview

```text
Track A — Foundation          Track B — Experience            Track C — Intelligence
─────────────────────         ─────────────────────           ─────────────────────
B0 Repo & CI baseline    →    B2 HomePilot Family tokens  →   B5 Ollabridge provider layer
B1 Domain data model     →    B3 App shell + sidebar +        B6 Coding workflow interface
   + core APIs                   settings dropdown               + GitPilot connector
                              B4 Command / Today engine        B7 Claude Code & Codex adapters
                                 + Focus Mode                  B8 Matrix Designer planner
                                                               B9 Email Sentinel + Calendar
                                                               B10 Documents & RAG pipeline

Track D — Trust & Scale (after B4 + first connector lands)
────────────────────────
B11 Approval Center, auth, RBAC, audit
B12 Scale: queues, pagination, indexes, load
B13 Mobile PWA, offline sync, notifications
B14 Observability, quality gates, release
```

Dependency rule of thumb: **B0–B1 unblock everything; B2–B3 unblock all UI batches; B5 unblocks every agent batch (all agents speak to models through Ollabridge); B11 must land before any connector is allowed to perform real writes in production.**

---

## Batch B0 — Repository, toolchain, and CI baseline

**Goal:** every later batch can be built, tested, and validated by CI with one command.
**Depends on:** nothing.

**Files:** `.github/workflows/ci.yml`, `Makefile`, `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `docker-compose.yml`, new `.env.example`.

**Work items**
1. Make `make install && make test` green from a clean clone (uv-managed Python + pnpm workspaces).
2. CI matrix: Python tests, TypeScript build + typecheck for every workspace package, ESLint/Ruff, `docker compose config` validation, `alembic upgrade head` against a disposable Postgres.
3. Add `.env.example` covering all variables referenced in README §11 plus new ones introduced by this plan (`OLLABRIDGE_URL`, `OLLABRIDGE_API_KEY`, `GITPILOT_URL`, `MATRIX_DESIGNER_URL`, `EMAIL_PROVIDER`, etc.).
4. Wire `packages/shared-types` as a real workspace dependency of `ui-bridge`, `operator-web`, and `mobile-pwa` (today the portal duplicates types via fixtures).

**Acceptance:** CI green on a fresh branch; compose stack boots; migrations apply.
**Closes TODO:** §9 "CI checks for Python tests, TypeScript builds, linting, Docker Compose config, and migration validity."

---

## Batch B1 — Domain data model and core APIs (thousands-of-tasks contract)

**Goal:** replace seeded fixtures with a persistent domain model designed from day one for thousands of tasks.
**Depends on:** B0.

**Files:** new Alembic migration `0002_daypilot_domain`, `services/knowledge-service/daypilot_knowledge/db/models.py` (extend), new `services/api-gateway/app/routers/{tasks,projects,documents,agents,plan}.py`, `packages/shared-types/src/index.ts`.

**Work items**
1. Tables: `tasks`, `projects`, `agent_runs`, `day_plans`, `plan_blocks`, `approvals`, `events`, `coding_runs`, `email_items`, `calendar_events` — with indexes on task `(owner, status, project_id, due_date)`, document `(project_id, status, source)`, agent run `(state, updated_at)` as required by TODO §7.
2. Cursor-based pagination + filter + sort contract on every list endpoint (`GET /v1/tasks?cursor=…&status=…&owner=…&sort=…`); no unbounded list responses anywhere.
3. `events` table + `GET /v1/events/stream` (SSE) carrying the Today Context event schema: `plan.updated`, `block.started`, `approval.requested`, `agent.state_changed`, `blocker.raised`.
4. Regenerate `packages/shared-types` from the FastAPI OpenAPI schema (or maintain a checked contract test) so TS and Python contracts cannot drift.
5. Seed script that loads realistic volume (5,000 tasks, 40 projects, 200 documents, 100 agent runs) for development and load testing.

**Acceptance:** contract tests pass; seeded 5k-task workspace lists any filtered page in <100 ms locally.
**Closes TODO:** §7 "pagination contracts", "database indexes", "event schema for Today Context changes"; foundation for §10 Projects/Agents rows.

---

## Batch B2 — HomePilot Family design token package and brand guide

**Goal:** DayPilot inherits the HomePilot design language through a shared, versioned token package instead of hand-written CSS variables.
**Depends on:** B0.

**Files:** new `packages/homepilot-theme/` (tokens.css, tokens.ts, icons/, motion.ts), new `docs/homepilot-family-brand-guide.md`, refactor `packages/ui-bridge/src/space-bridge.css` to consume tokens.

**Work items**
1. Extract the existing `--dp-*` variables into `packages/homepilot-theme` and reconcile them with HomePilot's frontend palette (obsidian/midnight surfaces, Apple Blue `#007aff`, Cyber Cyan `#00f0ff`, System Purple `#af52de`, Alert Orange `#ff9500`, System Green `#34c759`) into one canonical token set: color, typography scale, radii, spacing, elevation/shadow, blur, and motion durations/easings (adopt HomePilot's `fadeIn`/`msgSlideIn`/`glowPulse`-style motion vocabulary at calmer amplitudes).
2. Define the shared **state language** tokens + icon set: `local-first`, `approval-gated`, `ai-running`, `blocked`, `safe`, `needs-attention` — each with a color, icon, and pill treatment reused across Command, Agents, Documents, and Approvals.
3. Write `docs/homepilot-family-brand-guide.md`: principles (calm, premium, no enterprise clutter), token contract, light-on-dark rules, breakpoint definitions (phone <640, tablet <1024, desktop, wide ≥1440), and do/don't examples.
4. Refactor `space-bridge.css` to consume `homepilot-theme` tokens exclusively; delete hard-coded values.

**Acceptance:** UI renders identically or better from tokens only; brand guide reviewed; a token change (e.g. accent hue) propagates everywhere.
**Closes TODO:** §2 "shared design token package", "formal brand guide", "shared iconography and state language".

---

## Batch B3 — App shell refactor: navigation, drawers, and the settings dropdown

**Goal:** break the 624-line monolith portal into composable shell + views, and ship the **bottom-left sidebar settings dropdown (ChatGPT-style)**.
**Depends on:** B2.

**Files:** refactor `packages/ui-bridge/src/minimalPortal.tsx` into `src/shell/{AppShell,Sidebar,Drawer,CommandPalette}.tsx`, `src/views/{Command,Calendar,Tasks,Projects,Documents,Agents}.tsx`, new `src/shell/SettingsMenu.tsx`, new `src/settings/{SettingsPanel,ProvidersSettings,IntegrationsSettings,AppearanceSettings,PermissionsSettings}.tsx`.

**Work items**
1. Sidebar keeps the six first-class views (Command, Calendar, Tasks, Projects, Documents, Agents). Remove the `More: Inbox · GitPilot · Settings` text stub (`minimalPortal.tsx:584`).
2. **Settings dropdown:** a persistent button pinned to the bottom-left of the sidebar showing the user avatar + workspace name; clicking opens an upward drop-up menu (ChatGPT pattern) with: *Profile & workspace*, *Integrations* (GitPilot, Matrix Designer, Email, Calendar, Box, HomePilot), *AI Providers* (Ollabridge routing, model health), *Appearance* (HomePilot Family theme, density), *Permissions & approvals*, *Keyboard shortcuts*, *Sign out*. On phone the same menu anchors from the bottom tab bar. Full keyboard/ARIA support (menu role, Esc to close, focus trap).
3. Right-edge context drawer as a shared shell primitive (email/source/GitPilot/RAG telemetry) — no modals for context.
4. Command palette (⌘K) scaffold with actions registered per view; keyboard-first navigation across panes.
5. Integrations (HomePilot, GitPilot, Matrix Designer, Box, Email, Ollabridge) live only in Settings/drawers, never in primary nav — per README product rules.
6. Responsive shell: three layouts (rail + multipane desktop, collapsible tablet, bottom-tab phone) driven by the B2 breakpoints; validate on all three.

**Acceptance:** all six views route and render from live B1 APIs (falling back to seed data), settings drop-up works with mouse/keyboard/touch on desktop and phone widths, `test_ui_minimalist_contract.py` extended to assert the settings menu and nav contract.
**Closes TODO:** §2 "align navigation, drawer behavior, cards, command surfaces", "validate UI on desktop/tablet/phone breakpoints"; user requirement: settings button bottom-left dropdown.

---

## Batch B4 — Command experience: Today engine, Focus Mode, plan lifecycle, continuity

**Goal:** make the daily mental modes real: morning plan → focus → review → wrap → continue tomorrow.
**Depends on:** B1, B3.

**Files:** new `services/orchestrator/daypilot_orchestrator/{today_engine.py,plan_state.py,wrapup.py,continuity.py}`, gateway router `plan.py`, UI `src/views/Command.tsx`, `src/views/FocusMode.tsx`.

**Work items**
1. **Daily plan state machine** (`DRAFT → PROPOSED → APPROVED → ACTIVE → ADJUSTED → WRAPPED`): AI proposes the day (via Ollabridge in B5; deterministic heuristics until then), user approves or adjusts via chat; every block carries owner, source, status per README product rules.
2. **Today Context engine:** aggregates Now / Next / Later, AI-running count, blockers, approvals, projects-needing-attention into one `GET /v1/today` response; pushes deltas over the B1 event stream.
3. **Focus Mode** as a first-class Command action: hides all panes except the current block, its context, linked artifacts, and allowed actions; timer + "done / blocked / hand to AI" exits; registered in the command palette.
4. **End-of-day wrap-up:** generated summary of progress, unresolved risks, produced outputs, and tomorrow's draft plan; persisted as tomorrow's `DRAFT`.
5. **Continue-from-yesterday:** per-project continuity record (last state, linked documents, branches, blockers, next action) restored into the drawer and Command feed each morning.
6. Morning summary card exactly per README "Best Simple UX" (Now/Next/Later + counts + three actions).

**Acceptance:** a full simulated day (plan → approve → focus → wrap → next-morning continue) passes an end-to-end test; mental-mode table in TODO §3 is demonstrable.
**Closes TODO:** §3 all five checkboxes except mobile/offline (B13); §10 "Calendar: static seeded day plan" (plan side).

---

## Batch B5 — Ollabridge provider layer (default LLM provider)

**Goal:** every model call in DayPilot goes through Ollabridge — one OpenAI-compatible URL + key routing local/hybrid/cloud — with health, latency, and fallback visible in Settings.
**Depends on:** B0; unblocks B4's AI planning, B6–B10 agents.

**Files:** refactor `services/model-serving/daypilot_models/{connectors.py,router.py}`, new `ollabridge_client.py`, new `provider_health.py`, UI `src/settings/ProvidersSettings.tsx`.

**Work items**
1. `OllabridgeConnector` speaking the OpenAI-compatible API (`/v1/chat/completions`, `/v1/models`) against `OLLABRIDGE_URL`; keep the existing mock connector for tests and the direct-Ollama connector as an escape hatch.
2. Routing policy per agent role (Scheduler, Email Sentinel, Document Assistant, Project Analyst, coding agents): preferred model tags, latency budget, privacy tier (local-only for documents/personas by default — local-first posture), fallback chain.
3. Health loop: poll Ollabridge model list + measure p50/p95 latency per model; expose `GET /v1/providers/health`; degrade gracefully to mock with a visible "AI degraded" state token (B2 state language).
4. Providers panel in the settings dropdown: connected nodes/models, latency, routing policy, fallback order — read-only view first, editable policy second.
5. Never log prompt contents or keys; provider errors carry request IDs only.

**Acceptance:** with a live Ollabridge instance, the B4 planner and one agent generate real completions; with Ollabridge down, the UI shows degraded state and mock routing keeps the app usable.
**Closes TODO:** §10 "Ollabridge: conceptual provider → runtime routing, model health, latency, fallback policy, provider settings"; DoD item 4.

---

## Batch B6 — Coding workflow interface + GitPilot connector (default bridge)

**Goal:** a principal engineer can see and steer coding work across many repos: branch, PR, tests, generated patch, risk, next action — with GitPilot as the retro-compatible default executor.
**Depends on:** B1, B5.

**Files:** new `packages/mcp-contracts/coding-workflow.json`, new `services/orchestrator/daypilot_orchestrator/coding/{interface.py,gitpilot_adapter.py,risk.py}`, gateway router `coding.py`, UI `src/views/coding/{CodingBlocks,PatchReview}.tsx`.

**Work items**
1. **`CodingWorkflowAdapter` interface** shared by all executors: `create_run(task, repo, mode)`, `get_run(run_id)`, `get_diff(run_id)`, `get_tests(run_id)`, `cancel(run_id)` — returning normalized branch/PR/tests/diff/risk metadata. GitPilot, Claude Code, and Codex all implement this.
2. **GitPilot adapter** (default): drive `POST /api/v1/gitpilot/runs` (A2A-secured, Matrix-Bundle-compatible), map GitPilot's Ask/Auto/Plan modes to DayPilot policy (Ask ↔ approval-gated is the default; Auto only allowed for personas in `ENABLED_AUTONOMOUS_LIMITED`), ingest its controlled diff and test results. Retro-compatibility: adapter tolerates older GitPilot response shapes behind a version negotiation header.
3. **Risk scoring:** files-changed surface, test pass rate, diff size, touched-path sensitivity → low/medium/high risk on each coding block.
4. **Patch review UI:** human-readable AI summary of the change, file list, diff viewer, test results, risk badge, Approve / Request changes / Reject — approval required before any repository write or PR creation (enforced server-side, not just UI).
5. Review-window scheduling: approved-pending patches automatically get a review block proposed into the day plan (B4).
6. Coding workflow audit log rows for every run, diff, approval, and write.

**Acceptance:** end-to-end against a live or recorded GitPilot: task → run → diff → review → approve → PR created; write attempted without approval is rejected at the API layer with an audit record.
**Closes TODO:** §5 "coding workflow interface", "GitPilot connector", "approval checks before repo writes", "patch review UI", "test result ingestion and risk scoring", "coding workflow audit logs"; §10 GitPilot row; DoD item 3 (GitPilot half).

---

## Batch B7 — Claude Code and Codex optional executor adapters

**Goal:** the same coding blocks can execute through Claude Code or Codex where available, selected by routing policy.
**Depends on:** B6.

**Files:** `services/orchestrator/daypilot_orchestrator/coding/{claude_code_adapter.py,codex_adapter.py,provider_routing.py}`, settings UI extension.

**Work items**
1. Claude Code adapter (headless/SDK invocation) and Codex adapter implementing `CodingWorkflowAdapter`; both report capability flags (diff granularity, test execution, session continuity).
2. Provider routing policy for coding: default GitPilot; per-project or per-task override to Claude Code/Codex; Ollabridge-backed local coding agents as a final option. Policy editable in Settings → Integrations.
3. Contract test suite that runs identically against all three adapters (recorded fixtures), guaranteeing the normalized metadata shape.

**Acceptance:** switching executor in settings changes which backend runs a coding block with zero UI changes; adapter contract tests pass for all three.
**Closes TODO:** §5 "provider routing policy"; §10 Claude Code/Codex row; DoD item 3 (optional adapters half).

---

## Batch B8 — Matrix Designer planner and design-review integration

**Goal:** Matrix Designer is DayPilot's planner brain for project/design work: it turns ideas into Design Bundles and batch roadmaps that feed the day plan, and reviews UI/deck/document quality.
**Depends on:** B4, B5.

**Files:** new `services/orchestrator/daypilot_orchestrator/design/{matrix_designer_adapter.py,bundle_intake.py}`, gateway router `design.py`, UI `src/views/design/{DesignReview,BatchRoadmap}.tsx`.

**Work items**
1. MCP client to the Matrix Designer server: submit an idea/blueprint, receive a Design Bundle (architecture, acceptance criteria incl. visual, ordered batch roadmap).
2. **Bundle intake:** map a Design Bundle's batches into DayPilot project tasks and proposed calendar blocks; each batch becomes a coding block routable through B6/B7 (Matrix Designer designs → GitPilot builds, per the ecosystem contract).
3. Design review connector: submit screenshots/decks/documents, receive visual-quality reports; findings land in Projects and the Command Strategic Feed as needs-attention items.
4. Design review reports rendered with the B2 state language; suggestions convertible to tasks in one click.

**Acceptance:** an idea submitted from a project drawer returns a bundle whose batches appear as scheduled, executor-routable tasks; a screenshot review produces a report card in the project.
**Closes TODO:** §10 Matrix Designer row; DoD item 5.

---

## Batch B9 — Email Sentinel and calendar connectors

**Goal:** real inbox and calendar signal drives the day plan; nothing is ever sent or written without approval.
**Depends on:** B1, B4, B5.

**Files:** new `services/orchestrator/daypilot_orchestrator/email/{sentinel.py,providers/{gmail.py,graph.py,imap.py}}`, `calendar/providers/{google.py,m365.py}`, gateway routers `email.py`, `calendar.py`, UI drawer panels.

**Work items**
1. Provider connectors with OAuth (Gmail, Microsoft Graph) and IMAP fallback; incremental sync with cursor state; credentials only via the secrets backend (B11).
2. **Email Sentinel agent:** urgency/intent classification, action-item extraction, follow-up deadline detection, schedule-impact detection (meeting requests → plan conflicts), reply drafting in user style — all via Ollabridge routing, local-tier by default.
3. Draft-and-approve flow: drafts live in the Approval Center; `send` is a policy-gated MCP tool that hard-fails without an approval record.
4. Calendar connectors: Google Calendar + Microsoft 365 read/sync; scheduling writes (create/move events) are approval-gated drafts; conflict detection feeds Today Context.
5. Task extraction from emails and meeting notes into the task ledger with source links.

**Acceptance:** connected inbox produces classified items and drafts; approving a draft sends it and audits it; declining leaves the mailbox untouched; calendar conflicts appear in Command.
**Closes TODO:** §6 email/calendar checkboxes, "extract tasks from emails…"; §10 Calendar + Email rows; DoD item 6.

---

## Batch B10 — Documents pipeline: sources, parsers, indexing, Document AI

**Goal:** the Documents tab becomes the Today Context Engine over real files — local folders, Box, project vault — with version-safe generated outputs and RAG-backed chat.
**Depends on:** B1, B5; indexing queue arrives with B12 (use inline worker until then).

**Files:** extend `services/knowledge-service/daypilot_knowledge/{pipeline.py,parsers/,sources/{local.py,box.py},retrieval.py}`, gateway router `documents.py`, UI `src/views/Documents.tsx` three-pane layout.

**Work items**
1. **Local source permissions:** explicit folder grants (read+index only by default), stored as policy records; no scanning outside granted scopes.
2. **Box connector:** OAuth, scoped folder access, incremental sync.
3. Parsers for Word/Excel/PowerPoint/PDF/Markdown/HTML/images/CSV/JSON/YAML → internal AI-readable representation; originals are never modified; generated outputs saved as new versions in the DayPilot Vault.
4. Chunking → embeddings (Ollabridge embedding route) → Qdrant vector index + keyword/BM25 hybrid retrieval → citation assembly.
5. **Document AI chat:** chat with one document, a project folder, or "today's context"; answers carry citations; convert answers to tasks.
6. Automatic linking: documents ↔ calendar blocks ↔ project cards by project, time, and relevance ("why this matters today").
7. Project status rules engine: progress, risk, blockers, due dates, AI activity computed from linked tasks/docs/emails/code (feeds §6 last checkbox and Project cards).

**Acceptance:** granted folder ingests all supported formats; chat over a project folder returns cited answers; generating an output never touches the source file; documents appear linked on the relevant project and calendar block.
**Closes TODO:** §6 documents checkboxes + project status rules; §10 Documents + Projects rows; DoD item 2 (documents).

---

## Batch B11 — Approval Center, authentication, RBAC, audit, and injection defense

**Goal:** the trust layer: one approval queue governing every sensitive action, with identity, roles, secrets, audit, and prompt-injection controls.
**Depends on:** B1; **must land before B6/B9/B10 connectors perform real writes in production.** (Develop in parallel; gate production enablement on this batch.)

**Files:** new `services/api-gateway/app/{auth.py,rbac.py}`, `services/orchestrator/daypilot_orchestrator/approvals/{center.py,policies.py}`, `security/injection_guard.py`, UI `src/views/Approvals.tsx` + phone approval cards.

**Work items**
1. Authentication + workspace membership (local-first single user by default; OIDC for team deployments); session tokens on every API.
2. RBAC roles (owner, operator, reviewer, read-only) enforced at routers and MCP tool dispatch.
3. **Central Approval Center:** one queue for email sends, calendar writes, repo writes/PRs, file generation, persona enablement, external communications; each item shows human-readable summary, risk, diff/preview, and policy that triggered it; approve/reject with reason; full audit trail.
4. Policy enforcement at the API/tool layer (not UI): MCP host checks persona install state + tool contract risk + approval record before executing any write-behavior tool; `DAYPILOT_MCP_WRITE_ENABLED` / dry-run defaults preserved.
5. Secrets management integration (env-injected backend: Vault/SOPS/keyring) — no tokens in DB, logs, traces, or prompts; add a secret-scanning CI check.
6. Prompt-injection detection for retrieved documents and emails: instruction-pattern screening + provenance tagging; injected content can never grant tool permissions (flag → quarantine → surface in Approvals).
7. Audit export (JSONL/CSV), retention settings, data deletion and workspace reset workflows.

**Acceptance:** every sensitive route rejects unauthenticated/unauthorized calls; a simulated injection in a document is flagged and cannot trigger a tool; audit export reproduces every approval decision.
**Closes TODO:** §8 all checkboxes; §10 Approval Center + Security rows; DoD item 9.

---

## Batch B12 — Scale infrastructure: queues, durable runs, backpressure, load tests

**Goal:** thousands of tasks, documents, and agent runs stay fast and calm.
**Depends on:** B1; upgrades B6–B10 internals.

**Files:** new `services/orchestrator/daypilot_orchestrator/jobs/{queue.py,worker.py}` (Redis/arq or Celery), retention policy module, `tests/load/`.

**Work items**
1. Queue infrastructure for agent jobs and document indexing: durable job state, retries with backoff, cancellation, dead-letter surfacing into Agents view; migrate B10 indexing and B6 coding runs onto it.
2. Rate limits + backpressure on tool execution per persona and per provider (protects Ollabridge nodes and external APIs).
3. Incremental sync hardening for email/calendar/documents/Git metadata (cursors, dedupe, conflict handling).
4. Retention policies: traces, generated outputs, temporary chunks — configurable, enforced by a scheduled sweeper.
5. Load tests: 5k+ tasks / 1k documents / 200 concurrent agent runs; assert list latency, event-stream fan-out, and UI virtualization budgets (virtualized lists in Tasks/Documents ledgers).

**Acceptance:** load suite passes in CI (nightly); killing a worker mid-run resumes or fails cleanly with visible state; ledgers scroll smoothly at 5k rows.
**Closes TODO:** §7 remaining checkboxes (queues, load testing, retention); §10 Agents row (durable runtime); DoD item 8.

---

## Batch B13 — Mobile PWA, offline sync, notifications, continuity handoff

**Goal:** DayPilot is a true phone companion: fast check-in, compact cards, push-ready approvals, safe handoff to desktop.
**Depends on:** B3, B4, B11.

**Files:** `apps/mobile-pwa/` (real app: manifest, service worker, views), `apps/operator-web` PWA metadata, new `src/mobile/{TodayView,ApprovalCards,NowCard}.tsx` in ui-bridge, notification service in gateway.

**Work items**
1. Mobile-first **Today view**: compact Now / Next / Blocked / AI Running / Approvals cards; summaries, never dense tables; voice/short-command input into the Strategic Feed.
2. Dedicated mobile layouts for Command, Approvals, Documents (summaries), Projects (cards) using the B2 phone breakpoint and B3 bottom-tab shell (settings menu anchored there).
3. Installable PWA: manifest, icons, offline cache rules (app shell + last Today snapshot), update flow with "new version" toast.
4. Offline-friendly local state: cached Today Context + queued non-sensitive actions replayed on reconnect; sensitive actions (approvals) require live connection by policy.
5. Web Push notifications for approvals and blockers; notification → deep link → approval card; approval decisions on phone are full-fidelity (same policy path as desktop).
6. Desktop↔mobile continuity: current focus block and active approvals sync via the event stream; "handoff to desktop" resumes exact context.
7. Responsive screenshot/visual-regression tests (Playwright) across the three breakpoints for Command, Approvals, Documents, Projects.

**Acceptance:** Lighthouse PWA installability passes; airplane-mode reopen shows last Today; a push-notified approval can be decided on phone and is instantly reflected on desktop.
**Closes TODO:** §3 "mobile-first Today view", "offline-friendly sync"; §4 all checkboxes; §10 Mobile row; DoD item 7.

---

## Batch B14 — Observability, quality gates, and release readiness

**Goal:** the system is observable, evaluated, documented, and releasable by an enterprise operator.
**Depends on:** all prior batches (final hardening pass).

**Files:** `services/observability/daypilot_observability/` (real OTel wiring), `infra/monitoring/` dashboards, `docs/` updates, `.github/workflows/` release pipelines, `tests/` expansion.

**Work items**
1. OpenTelemetry tracing across gateway → orchestrator → MCP host → knowledge service → model serving (Ollabridge spans included); structured JSON logs with request + workspace IDs everywhere.
2. Prometheus dashboards + alerts: requests, agent runs, approval latency, model latency per Ollabridge route, indexing jobs, failures; production SLOs documented.
3. RAG quality evaluations (precision, recall, faithfulness, citation coverage) as a scheduled scorecard using `docs/rag-evaluation.md` metrics; regression gate in CI.
4. UI smoke tests for all six views + settings dropdown + Focus Mode + Approval flow (Playwright), wired into CI with the B13 visual regression suite.
5. Docs refresh: architecture, deployment, security updated to as-built; operator runbook (backup/restore, key rotation, incident response); `TODO.md` checkboxes reconciled.
6. Release pipeline: desktop (Tauri) build, web/PWA deploy to `daypilot.ruslanmv.com`, versioned migrations, rollback procedure.

**Acceptance:** the Definition of Done list in `TODO.md` §11 passes end to end on a staged deployment.
**Closes TODO:** §9 all checkboxes; §10 Observability + Testing rows; DoD item 10.

---

## 4. Traceability: TODO.md → batches

| TODO section | Batches |
|---|---|
| §2 HomePilot Family design | B2, B3 |
| §3 Daily usage & mental modes | B4 (+ B13 mobile/offline) |
| §4 Phone + desktop portability | B13 (+ B3 shell) |
| §5 AI workflow execution / coding | B5, B6, B7 |
| §6 Documents, email, calendar, projects | B9, B10 |
| §7 Scalability for thousands of tasks | B1, B12 |
| §8 Security, governance, compliance | B11 |
| §9 Observability & quality gates | B0, B14 |
| §10 Placeholder inventory | B1–B14 as mapped per row above |
| §11 Definition of Done | verified in B14 |

## 5. Suggested execution order

Solo/serial: **B0 → B1 → B2 → B3 → B5 → B4 → B6 → B11 → B9 → B10 → B7 → B8 → B12 → B13 → B14.**

Parallel (two streams after B1): Experience stream **B2→B3→B4→B13** alongside Intelligence stream **B5→B6→B7/B8/B9/B10**, with **B11** developed early in either stream and required before any real external write, and **B12/B14** closing.

Each batch should land as one reviewed changeset on its own branch, with its acceptance criteria demonstrated in the PR description — the same approval-first discipline DayPilot enforces for its own agents.
