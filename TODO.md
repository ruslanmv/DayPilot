# DayPilot Enterprise TODO and Production Completion Plan

DayPilot Enterprise is intended to become a premium, daily-use AI operating system for professional work. This document tracks the placeholders that must be completed before the product can be considered production-ready at enterprise quality.

> **Execution plan:** every placeholder below is mapped to an ordered, dependency-aware batch in [`docs/production-plan.md`](docs/production-plan.md). Use that roadmap (batches B0–B14) to generate and refactor the code; tick checkboxes here as each batch lands.

## 1. Product North Star

DayPilot should optimize the user's day by combining planning, execution, monitoring, and continuity across calendar, tasks, projects, documents, agents, email, coding workflows, and design review.

```text
DayPilot = Calendar + Tasks + Projects + Agents + Documents + Natural Tools
```

The application must be designed for an AI/ML Principal Engineer or technical executive who can have thousands of tasks, many projects, multiple codebases, client obligations, internal initiatives, inbox pressure, agent runs, and document workflows active at the same time.

The app should answer these questions every day:

1. What should I do now?
2. What can AI do for me?
3. Which workflow is blocked?
4. Which document or project needs attention?
5. Which code task needs review?
6. Which approval is required before an agent writes or sends anything?
7. What changed since yesterday?
8. What can continue automatically without distracting me?

## 2. HomePilot Family Design Requirement

DayPilot must feel like part of the **HomePilot Family** rather than a disconnected enterprise dashboard.

### Theme and UX expectations

- Premium, calm, high-quality UI with the same design discipline as HomePilot.
- Local-first privacy posture and portable persona concepts inherited from HomePilot.
- Shared visual language: dark premium workspace, calm surfaces, refined spacing, purposeful accent colors, and no noisy enterprise clutter.
- Family consistency across desktop, web, and mobile PWA.
- Clear distinction between personal/local context from HomePilot and professional/work execution in DayPilot.
- Persona portability through `.hpersona` packages and governed enablement.

### Placeholder work

- [x] Define a shared HomePilot/DayPilot design token package for color, typography, radii, spacing, shadows, and motion. _(Batch B2)_
- [x] Add a formal HomePilot Family brand guide under `docs/`. _(Batch B2)_
- [x] Align DayPilot navigation, drawer behavior, cards, and command surfaces with HomePilot design principles. _(Batch B3)_
- [x] Add shared iconography and state language for local-first, approval-gated, AI-running, blocked, and safe states. _(Batch B2)_
- [ ] Validate the UI on desktop, tablet, and phone breakpoints.

## 3. Daily Usage and Mental Models

DayPilot must be designed for daily use, not occasional administration. The user should open it every morning and trust it as the operating room for the day.

### Primary mental modes

| Mode | User question | DayPilot behavior |
|---|---|---|
| Morning planning | What is my day? | Summarize Now, Next, Later, AI running, blockers, documents, and approvals. |
| Focus execution | What do I do now? | Start focus mode, hide noise, show only current block, context, and allowed actions. |
| AI delegation | What can AI do? | Route coding, document, email, design, and scheduling tasks to agents. |
| Review and approval | What needs me? | Show only decisions that require human approval. |
| Project continuity | Where did I stop? | Restore yesterday's state, linked documents, branches, blockers, and next action. |
| Mobile check-in | What changed while away? | Show compact Now, Blocked, AI Running, and Approvals views on phone. |
| End-of-day wrap | What happened and what is tomorrow? | Summarize progress, unresolved risks, generated outputs, and tomorrow's draft plan. |

### Placeholder work

- [x] Implement Focus Mode as a first-class Command action. _(Batch B4)_
- [x] Add a true daily plan approval state machine. _(Batch B4)_
- [x] Add end-of-day wrap-up generation. _(Batch B4)_
- [x] Add “continue from yesterday” memory across projects, documents, coding branches, and agent runs. _(Batch B4)_
- [x] Add mobile-first Today view for phone usage. _(Batch B13)_
- [x] Add offline-friendly local state sync for desktop and PWA. _(Batch B13 — cached Today snapshot + service worker)_

## 4. Portable Phone and Desktop Experience

DayPilot must work as a premium desktop command center and a portable phone companion.

### Desktop expectations

- Multi-pane command center.
- Keyboard-first workflow.
- Deep drawer context.
- Coding/project/document review surfaces.
- Local model provider visibility through Ollabridge.

### Phone expectations

- Fast daily check-in.
- Compact Now / Next / Blocked / Approval cards.
- Push-ready approval workflows.
- Voice or short-command input.
- Document and project summaries, not dense tables.
- Safe handoff back to desktop for deep work.

### Placeholder work

- [x] Add dedicated mobile PWA layouts for Command, Approvals, Documents, and Projects. _(Batch B13 — mobile Today shell + bottom tabs)_
- [x] Add responsive screenshot tests or visual regression checks. _(Batch B13 — Playwright phone-viewport verification)_
- [x] Add installable PWA metadata, offline cache rules, and update flow. _(Batch B13 — manifest + icon + service worker + skipWaiting update flow)_
- [x] Add notification and approval handoff strategy. _(Batch B13 — Web Push scaffold + notification deep-link; approvals require live connection)_
- [x] Add desktop-to-mobile continuity for current focus block and active approvals. _(Batch B13 — cached Today snapshot + /v1/today refresh)_

## 5. AI Workflow Execution

DayPilot should not only display work. It should execute safe workflows through agents and integrations.

### Default tool roles

| Tool or agent | Default role |
|---|---|
| Ollabridge | Default LLM provider abstraction for local/hybrid model routing. |
| GitPilot | Default retro-compatible coding workflow bridge. |
| Claude Code | Optional coding workflow executor where available. |
| Codex | Optional coding workflow executor where available. |
| Matrix Designer | Planner and design-quality reviewer for UI, decks, reports, and product surfaces. |
| Email Sentinel | Inbox monitor, urgency classifier, response drafter, and schedule-impact detector. |
| Document Assistant | Reads, summarizes, compares, and turns documents into tasks or outputs. |
| Project Analyst | Scores risk, tracks progress, and connects tasks, docs, email, and code. |
| Scheduler | Builds and adjusts the minute-by-minute day plan. |
| Approval Center | Shows only human decisions required before sensitive actions. |

### Coding workflow requirements

DayPilot should optimize coding workflows for a principal engineer managing many repositories and agent tasks.

- GitPilot is the default bridge for backwards-compatible coding workflows.
- Claude Code and Codex should be supported as optional execution backends.
- Coding blocks should connect branch, PR, tests, generated patch, risk score, files changed, and suggested next action.
- Write actions must be approval-gated by default.
- DayPilot should schedule review windows for generated patches.
- DayPilot should summarize agent changes in human-readable form before approval.

### Placeholder work

- [x] Define a coding workflow interface shared by GitPilot, Claude Code, and Codex adapters. _(Batch B6)_
- [x] Add a GitPilot connector service or MCP adapter with branch, PR, tests, and diff metadata. _(Batch B6)_
- [x] Add provider routing policy for GitPilot, Claude Code, Codex, and Ollabridge-backed coding agents. _(Batch B7)_
- [x] Add approval checks before repository writes, shell commands, or PR creation. _(Batch B6)_
- [x] Add generated patch review UI. _(Batch B6)_
- [x] Add test result ingestion and risk scoring. _(Batch B6)_
- [x] Add coding workflow audit logs. _(Batch B6)_

## 6. Documents, Email, Calendar, and Projects

Documents and email are daily work inputs. Calendar and projects turn them into time and progress.

### Placeholder work

- [x] Implement real local file source permissions. _(Batch B10 — granted-scope registry, read+index by default)_
- [ ] Implement Box connector authentication and scoped folder access.
- [x] Implement document ingestion for Word, Excel, PowerPoint, PDF, Markdown, images, and project data. _(Batch B10 — parser registry; office/pdf via optional extras)_
- [x] Preserve original files and write generated outputs as new versions only. _(Batch B10 — version-safe generate)_
- [x] Add email provider connectors such as Gmail, Microsoft Graph, and IMAP. _(Batch B9 — IMAP/SMTP content plane + mock; Gmail/Microsoft via the imap_smtp plane)_
- [x] Add calendar provider connectors such as Google Calendar and Microsoft 365. _(Batch B9 — connectors + conflict detection; approval-gated event drafts)_
- [ ] Link documents to calendar blocks and project cards automatically.
- [x] Extract tasks from emails, documents, meeting notes, and code review summaries. _(Batch B9 — email → task; docs in B10)_
- [x] Add project status rules for progress, risk, blockers, due dates, and AI activity. _(Batch B10)_

## 7. Scalability for Thousands of Tasks

DayPilot must be optimized for thousands of tasks, documents, agent runs, and project signals without overwhelming the user.

### Industry-practice requirements

- Use server-side pagination, filtering, and sorting for large ledgers.
- Use background indexing queues for document and email ingestion.
- Use durable job state for agent runs.
- Use structured event streams for plan changes and approvals.
- Use incremental sync for email, calendar, documents, and Git metadata.
- Use vector and keyword retrieval for project memory.
- Use audit tables for approvals and high-risk actions.
- Use rate limits and backpressure for tool execution.

### Placeholder work

- [x] Add queue infrastructure for agent jobs and document indexing. _(Batch B12 — durable DB-backed queue, retries/backoff/dead-letter)_
- [x] Add pagination contracts to tasks, documents, projects, and agent runs. _(Batch B1)_
- [x] Add database indexes for task owner/status/project/date, document project/status/source, and agent run state. _(Batch B1)_
- [x] Add event schema for Today Context changes. _(Batch B1)_
- [x] Add load testing for thousands of tasks and documents. _(Batch B12 — volume pagination + latency budget test; make seed for 5k)_
- [x] Add retention policies for traces, generated outputs, and temporary document chunks. _(Batch B12 — retention sweep)_

## 8. Security, Governance, and Compliance

DayPilot must follow enterprise-safe defaults.

### Required safeguards

- No destructive file edits by default.
- No external sending without approval.
- No repository writes without approval.
- No private folder scanning without explicit permission.
- No persona activation without policy review.
- No raw secrets in logs, traces, prompts, or generated summaries.
- All sensitive actions require audit records.

### Placeholder work

- [x] Add authentication and workspace membership. _(Batch B11 — local-first default, token+role for teams)_
- [x] Add role-based access control. _(Batch B11 — ranked roles, require_role gates)_
- [x] Add secrets management integration. _(Batch B11 — env/managed abstraction + redaction + gitleaks CI)_
- [x] Add approval policy enforcement at the API/tool layer. _(Batch B11 — central Approval Center, RBAC-gated decisions)_
- [x] Add prompt-injection detection for documents and emails. _(Batch B11 — injection guard wired into Document AI)_
- [x] Add audit export and retention settings. _(Batch B11 — JSONL/CSV audit export)_
- [ ] Add data deletion and workspace reset workflows.

## 9. Observability and Quality Gates

DayPilot should be observable before production use.

### Placeholder work

- [x] Add OpenTelemetry tracing across gateway, orchestrator, MCP host, knowledge service, and model serving. _(Batch B14 — request tracing/span boundary + traces service; OTel exporter hook)_
- [x] Add Prometheus dashboards for requests, agent runs, approval latency, model latency, indexing jobs, and failures. _(Batch B14 — Grafana dashboard + alert rules)_
- [x] Add structured JSON logs with request IDs and workspace IDs. _(Batch B14 — gateway observability middleware, secrets redacted)_
- [x] Add RAG quality evaluations for retrieval precision, recall, faithfulness, and citation coverage. _(Batch B14 — rag_eval scorecard + CI-ready gate)_
- [x] Add UI smoke tests for Command, Calendar, Tasks, Projects, Documents, and Agents. _(Batch B14 — Playwright smoke, make ui-smoke)_
- [x] Add CI checks for Python tests, TypeScript builds, linting, Docker Compose config, and migration validity. _(Batch B0)_

## 10. Current Placeholder Inventory

The current scaffold includes strong product direction and UI fixtures, but the following must be completed for a production-grade release:

| Area | Placeholder today | Needed for production |
|---|---|---|
| Calendar | Static seeded day plan | Real calendar providers, conflict handling, scheduling writes with approval. |
| Email | Static Email Sentinel state | Gmail/Graph/IMAP connectors, incremental sync, drafts, approval before send. |
| Documents | Seed documents and source cards | Real local/Box connectors, permission model, parsers, indexing, generated output storage. |
| Projects | Seed project cards | Persistent project model, progress/risk engine, due dates, linked artifacts. |
| Agents | Seed agent rows | Durable agent runtime, queues, retries, cancellation, audit logs. |
| GitPilot | UI references only | Real connector for branches, PRs, tests, diffs, patch review, and write approvals. |
| Claude Code / Codex | Not wired | Optional executor adapters behind the coding workflow interface. |
| Ollabridge | Conceptual provider | Runtime routing, model health, latency, fallback policy, provider settings. |
| Matrix Designer | Seed design notes | Design review connector, screenshot/deck analysis, visual quality reports. |
| Approval Center | Drawer concepts | Central approval queue, policy enforcement, audit trail. |
| Mobile | PWA scaffold | Mobile-optimized Today, approval, and notification workflows. |
| Observability | Foundational modules | End-to-end tracing, dashboards, alerting, retention, and production SLOs. |
| Security | Policy docs | Auth, RBAC, secrets, data boundaries, prompt-injection controls. |
| Testing | Initial tests | CI matrix, UI smoke tests, load tests, migration tests, connector contract tests. |

## 11. Definition of Done for Enterprise Release

DayPilot can be considered enterprise production-ready when:

1. The user can plan, execute, monitor, and continue a real workday from Command.
2. Calendar, email, documents, projects, agents, and coding workflows use real connectors or approved mocks with the same contracts.
3. GitPilot works as the default coding bridge, with Claude Code and Codex available as optional adapters.
4. Ollabridge routes model providers with health, latency, and fallback visibility.
5. Matrix Designer can review UI/deck/document quality and feed suggestions back into Projects and Command.
6. Email Sentinel can classify inbox work and draft responses without sending until approved.
7. The app works well on desktop and phone.
8. Thousands of tasks and documents remain searchable, filterable, and summarized without UI overload.
9. All sensitive actions are approval-gated, audited, and reversible where possible.
10. Documentation, tests, observability, deployment, and security controls are complete enough for an enterprise operator to run and maintain the system.
