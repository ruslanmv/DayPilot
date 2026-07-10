# DayPilot Enterprise TODO and Production Completion Plan

DayPilot Enterprise is intended to become a premium, daily-use AI operating system for professional work. This document tracks the placeholders that must be completed before the product can be considered production-ready at enterprise quality.

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

- [ ] Define a shared HomePilot/DayPilot design token package for color, typography, radii, spacing, shadows, and motion.
- [ ] Add a formal HomePilot Family brand guide under `docs/`.
- [ ] Align DayPilot navigation, drawer behavior, cards, and command surfaces with HomePilot design principles.
- [ ] Add shared iconography and state language for local-first, approval-gated, AI-running, blocked, and safe states.
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

- [ ] Implement Focus Mode as a first-class Command action.
- [ ] Add a true daily plan approval state machine.
- [ ] Add end-of-day wrap-up generation.
- [ ] Add “continue from yesterday” memory across projects, documents, coding branches, and agent runs.
- [ ] Add mobile-first Today view for phone usage.
- [ ] Add offline-friendly local state sync for desktop and PWA.

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

- [ ] Add dedicated mobile PWA layouts for Command, Approvals, Documents, and Projects.
- [ ] Add responsive screenshot tests or visual regression checks.
- [ ] Add installable PWA metadata, offline cache rules, and update flow.
- [ ] Add notification and approval handoff strategy.
- [ ] Add desktop-to-mobile continuity for current focus block and active approvals.

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

- [ ] Define a coding workflow interface shared by GitPilot, Claude Code, and Codex adapters.
- [ ] Add a GitPilot connector service or MCP adapter with branch, PR, tests, and diff metadata.
- [ ] Add provider routing policy for GitPilot, Claude Code, Codex, and Ollabridge-backed coding agents.
- [ ] Add approval checks before repository writes, shell commands, or PR creation.
- [ ] Add generated patch review UI.
- [ ] Add test result ingestion and risk scoring.
- [ ] Add coding workflow audit logs.

## 6. Documents, Email, Calendar, and Projects

Documents and email are daily work inputs. Calendar and projects turn them into time and progress.

### Placeholder work

- [ ] Implement real local file source permissions.
- [ ] Implement Box connector authentication and scoped folder access.
- [ ] Implement document ingestion for Word, Excel, PowerPoint, PDF, Markdown, images, and project data.
- [ ] Preserve original files and write generated outputs as new versions only.
- [ ] Add email provider connectors such as Gmail, Microsoft Graph, and IMAP.
- [ ] Add calendar provider connectors such as Google Calendar and Microsoft 365.
- [ ] Link documents to calendar blocks and project cards automatically.
- [ ] Extract tasks from emails, documents, meeting notes, and code review summaries.
- [ ] Add project status rules for progress, risk, blockers, due dates, and AI activity.

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

- [ ] Add queue infrastructure for agent jobs and document indexing.
- [ ] Add pagination contracts to tasks, documents, projects, and agent runs.
- [ ] Add database indexes for task owner/status/project/date, document project/status/source, and agent run state.
- [ ] Add event schema for Today Context changes.
- [ ] Add load testing for thousands of tasks and documents.
- [ ] Add retention policies for traces, generated outputs, and temporary document chunks.

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

- [ ] Add authentication and workspace membership.
- [ ] Add role-based access control.
- [ ] Add secrets management integration.
- [ ] Add approval policy enforcement at the API/tool layer.
- [ ] Add prompt-injection detection for documents and emails.
- [ ] Add audit export and retention settings.
- [ ] Add data deletion and workspace reset workflows.

## 9. Observability and Quality Gates

DayPilot should be observable before production use.

### Placeholder work

- [ ] Add OpenTelemetry tracing across gateway, orchestrator, MCP host, knowledge service, and model serving.
- [ ] Add Prometheus dashboards for requests, agent runs, approval latency, model latency, indexing jobs, and failures.
- [ ] Add structured JSON logs with request IDs and workspace IDs.
- [ ] Add RAG quality evaluations for retrieval precision, recall, faithfulness, and citation coverage.
- [ ] Add UI smoke tests for Command, Calendar, Tasks, Projects, Documents, and Agents.
- [ ] Add CI checks for Python tests, TypeScript builds, linting, Docker Compose config, and migration validity.

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
