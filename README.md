# DayPilot Enterprise

<p align="center">
  <strong>Local-first AI operator workspace for professional workflows.</strong><br />
  Governed multi-agent orchestration, HomePilot persona portability, MCP tool contracts, private RAG memory, and production-grade observability.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Enterprise%20Ready-blue?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Domain-daypilot.ruslanmv.com-cyan?style=for-the-badge" alt="Domain" />
  <img src="https://img.shields.io/badge/Stack-Tauri%20%2B%20React%20%2B%20FastAPI-purple?style=for-the-badge" alt="Stack" />
  <img src="https://img.shields.io/badge/Integration-HomePilot%20.hpersona-orange?style=for-the-badge" alt="HomePilot" />
</p>

---


## Enterprise Production Readiness

DayPilot Enterprise is organized as a production-oriented monorepo for local-first and hybrid AI operations. The repository separates operator experience, API ingress, orchestration, MCP tool governance, knowledge retrieval, model routing, voice workflows, observability, local data, infrastructure, and shared TypeScript contracts.

### Production principles

- **Local-first by default:** sensitive documents, personas, project memory, and approval state are designed to run locally unless a deployment explicitly enables cloud synchronization.
- **Human approval for write actions:** email sends, calendar changes, repository writes, file generation, persona enablement, and external communications must be approval-gated.
- **Auditable execution:** agent plans, tool calls, document indexing, model requests, approvals, and errors should emit structured logs, traces, metrics, and audit records.
- **Provider abstraction:** Ollabridge routes local or hybrid model execution so the UX does not depend on raw model configuration during daily work.
- **Document safety:** source files are preserved; DayPilot creates AI-readable internal representations and writes generated outputs as new versions only.
- **Composable deployment:** desktop, local web, Docker Compose, Kubernetes, Terraform, and cloud gateway modes are documented separately so teams can choose the right operational footprint.

### Repository map

| Area | Path | Purpose |
|---|---|---|
| Operator web UI | `apps/operator-web` | React/Vite web operator experience. |
| Desktop shell | `apps/operator-desktop` | Tauri desktop wrapper for local workstations. |
| Mobile PWA | `apps/mobile-pwa` | Mobile-friendly operator view. |
| UI bridge package | `packages/ui-bridge` | Shared DayPilot command-center UI components and styling. |
| Shared contracts | `packages/shared-types` | TypeScript domain contracts for personas, approvals, tasks, projects, agents, and documents. |
| API gateway | `services/api-gateway` | FastAPI ingress for health, operator briefing, persona preview, and future external API routes. |
| Orchestrator | `services/orchestrator` | Approval-first agent runtime and workflow planning. |
| MCP host | `services/mcp-host` | Governed tool registry and HomePilot `.hpersona` bridge. |
| Knowledge service | `services/knowledge-service` | Document ingest, chunk persistence, and retrieval foundation. |
| Model serving | `services/model-serving` | Mock/Ollama/OpenAI-compatible routing layer. |
| Voice gateway | `services/voice-gateway` | Future ASR/TTS and live voice workflow contracts. |
| Observability | `services/observability` | Metrics, traces, and structured logging utilities. |
| Local data | `local_data` | Local-first runtime storage placeholders for documents, indexes, traces, and personas. |
| Infrastructure | `infra` | Docker, Kubernetes, and Terraform deployment assets. |
| Tests | `tests` | Python service and contract tests. |

### Production deployment checklist

Before a production deployment, verify the following operational controls:

1. **Identity and access:** configure authentication, workspace membership, and admin-only policy management.
2. **Secrets:** store credentials in a managed secret backend; never commit provider tokens, email credentials, Box credentials, or model API keys.
3. **Database:** run Alembic migrations and configure backup/restore for Postgres or the chosen production database.
4. **Document permissions:** explicitly approve local folders, Box scopes, and project vault write permissions. Default to read + index only.
5. **MCP tools:** review every tool contract for risk level, write behavior, approval requirement, persona access, and workspace scope.
6. **Model routing:** define Ollabridge local/hybrid/cloud routing and fallback rules per agent role.
7. **Observability:** enable metrics, traces, structured logs, retention policy, alerts, and audit exports.
8. **Network boundaries:** expose only the gateway or approved ingress; keep local services and data stores private.
9. **Approvals:** test human-in-the-loop flows for email, calendar, Git, document generation, and external communications.
10. **Disaster recovery:** document restore steps for database, vector index, generated files, and persona registry.

## DayPilot Pro Premium UX Architecture

DayPilot Pro is designed as a daily AI operating room, not a passive dashboard. The product promise is:

```text
DayPilot = Calendar + Tasks + Projects + Agents + Documents + Natural Tools
```

The user should open DayPilot and immediately understand what to do now, what AI is doing, which project needs attention, what changed since yesterday, which document supports the work, and what needs approval.

### Best Simple UX

The default Command screen should reduce the morning to a single calm summary:

```text
Good morning. Here is your day.

NOW:      Continue DayPilot UI implementation
NEXT:     Review GitPilot generated patch
LATER:    Matrix Designer feedback + client follow-up

AI RUNNING: 4 workflows
BLOCKERS:   1 needs your approval
PROJECTS:   6 active, 2 need attention

[Start Focus Mode] [Review AI Work] [Adjust Plan]
```

DayPilot should not make the user search. It should answer:

- What should I do now?
- What is AI doing for me?
- Which project needs attention?
- What changed since yesterday?
- What needs my approval?

### Core Workflow

```text
Open DayPilot
   ↓
DayPilot reads calendar, email, projects, GitPilot, HomePilot, Matrix Designer
   ↓
AI creates a plan for the day
   ↓
User approves or adjusts with chat
   ↓
DayPilot schedules work blocks
   ↓
AI agents execute background tasks
   ↓
DayPilot monitors progress and blockers
   ↓
User continues work across projects without losing context
```

### Sidebar Structure

The default sidebar stays simple and first-class:

```text
Command
Calendar
Tasks
Projects
Documents
Agents
```

Connected systems such as HomePilot, GitPilot, Matrix Designer, Box, Local Files, Email, and Ollabridge belong in Settings or integration drawers rather than the primary nav.

### Main Screens

1. **Command — Daily Control Center**: the default screen with the Now / Next / Later summary, Strategic Feed, Today’s Plan, and live context for blockers, AI work, approvals, and project attention.
2. **Calendar — Minute-by-Minute AI Plan**: the actual day distribution, where every block has an owner, source, status, and drawer actions.
3. **Tasks — You vs AI**: manual commitments stay separate from work DayPilot is doing in the background.
4. **Projects — Continue Consulting and Internal Work**: each project shows progress, blocker state, AI activity, linked documents, and a Continue Work action. The drawer explains what was done yesterday, what needs to happen today, what AI is doing, linked files/branches/emails, blockers, and the next recommended action.
5. **Documents — AI File Command Center**: local files, Box, project folders, and the DayPilot Vault are organized by project, time, and relevance. Documents can be chatted with, summarized, compared, converted to tasks, or used to generate Office outputs without overwriting originals.
6. **Agents — AI Workflow Control**: HomePilot, GitPilot, Matrix Designer, Email Sentinel, Scheduler, Document Assistant, and Project Analyst work stays visible through simple Running, Needs Approval, and Blocked statuses.


### Documents Tab

Documents are a first-class DayPilot tab because most daily work lives in contracts, Excel sheets, Word reports, PowerPoint decks, PDFs, project notes, invoices, meeting files, proposals, screenshots, and code/design specs. The Documents tab is not a raw file browser; it is a **Today Context Engine** organized into three panes:

- **Sources**: Local PC files, Box, selected project folders, generated outputs, and the DayPilot Project Vault.
- **Smart Document Workspace**: today’s documents, project files, recent files, and files needing review.
- **Document AI**: chat with one document, a project folder, or all files relevant to today.

Supported default business formats include Word (`.doc`, `.docx`, `.rtf`, `.odt`), Excel (`.xls`, `.xlsx`, `.xlsm`, `.csv`, `.tsv`, `.ods`), PowerPoint (`.ppt`, `.pptx`, `.odp`), documents (`.pdf`, `.txt`, `.md`, `.html`), design references (`.png`, `.jpg`, `.webp`, `.svg`), and project data (`.json`, `.yaml`, `.xml`, `.sql`).

The safety model is explicit: source files stay untouched, DayPilot extracts readable text/tables/slides into an internal AI-readable representation, AI indexes chunks into project memory, users chat with the document, and generated outputs are saved as new versions.

### Integration Roles

| System | Role |
|---|---|
| HomePilot | Local context, personal workflows, environment signals, personas |
| GitPilot | Coding tasks, branches, PRs, tests, patches, code review |
| Matrix Designer | UI/UX suggestions, design review, layout critique, product quality |
| DayPilot | Daily planning, scheduling, task control, monitoring, approvals |
| Documents | Word, Excel, PowerPoint, PDF, notes, images, Box, local folders, and project vault memory |
| Ollabridge | AI provider layer for local/online model execution |

### Product Rules

1. Show only Now, Next, Blocked, AI Running, Project Progress, and Needs Approval by default.
2. Keep everything else in drawers or project detail views.
3. My Tasks are things the user must do manually.
4. AI Tasks are things DayPilot is doing for the user.
5. Every calendar block has an owner, source, and status.
6. Every project has yesterday, today, AI activity, linked documents, blockers, and next recommended action.
7. Every document explains why it matters today, which project/meeting needs it, what changed, and what AI can prepare from it.
8. Original Office and legacy files are never overwritten automatically; DayPilot creates AI-readable representations and saves generated outputs as new versions.
9. Default document permissions are read + index only, with no destructive edits and no external sharing without approval.
10. AI can prepare and execute safe workflows, but important actions require approval.
11. The user should be able to continue consulting and internal projects without losing context.

### Final Product Definition

DayPilot is a personal AI command center that organizes the day, executes safe AI workflows, monitors projects, coordinates HomePilot, GitPilot, and Matrix Designer, and helps the user continue work across consulting and internal projects with minimal effort.


## Local Development with Make and UV

DayPilot uses a UV-managed Python environment and a Makefile for a predictable local workflow:

```bash
make help      # list all supported commands
make install   # uv sync --group dev, then pnpm install
make run       # run the FastAPI API gateway with uvicorn
make run-web   # run the operator web app
make test      # run Python tests and package tests
```

The default Python install is intentionally lean (`uv sync --group dev`). Optional heavier extras for RAG, model serving, and observability can be installed with `make install-python-all`.


## Documentation Guide

The `docs/` folder is the production knowledge base for implementation, deployment, security, and operating-model decisions. Start with the architecture and security documents, then move into deployment and integration guides.

| Document | Audience | What it explains |
|---|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Engineers and architects | Service boundaries, operator UI → API gateway → orchestrator → MCP host → tools/knowledge/models flow, approval queue, and observability placement. |
| [`docs/security.md`](docs/security.md) | Security, platform, and product owners | Policy-first defaults, high-risk actions, approval requirements, and production prompt-injection/security expectations. |
| [`docs/deployment.md`](docs/deployment.md) | DevOps and platform teams | Local desktop, local web, cloud gateway, hybrid deployment modes, canonical domain, and Docker Compose baseline. |
| [`docs/operationalization-gap-analysis.md`](docs/operationalization-gap-analysis.md) | Technical leads | What production-readiness gaps were identified, which infrastructure/runtime files close them, and which areas still require hardening. |
| [`docs/homepilot-integration.md`](docs/homepilot-integration.md) | Integration engineers | `.hpersona` import flow, dependency inspection, restrictive policy creation, and safe enablement stages for HomePilot personas. |
| [`docs/persona-policy.md`](docs/persona-policy.md) | Governance and agent developers | Persona install states, allowed tools, blocked actions, rate limits, scopes, retention, and approval rules. |
| [`docs/mcp-tool-contracts.md`](docs/mcp-tool-contracts.md) | Tool developers | Required MCP tool metadata: input/output schemas, risk level, write behavior, approvals, personas, and workspace scopes. |
| [`docs/rag-evaluation.md`](docs/rag-evaluation.md) | AI quality and retrieval engineers | RAG evaluation placeholders for precision, recall, faithfulness, relevance, citations, retrieval gaps, and prompt-injection risk. |
| [`docs/ux-space-bridge-minimalist-portal.md`](docs/ux-space-bridge-minimalist-portal.md) | Product, design, and frontend | Premium minimalist portal principles, visual token contract, command-first flow, drawer behavior, and UI architecture. |
| [`docs/roadmap.md`](docs/roadmap.md) | Product and delivery teams | Sequenced roadmap from HomePilot import and persona registry to approvals, connectors, RAG, observability, and voice gateway. |

### Recommended reading paths

- **First-time developer:** `README.md` → `docs/architecture.md` → `docs/security.md` → `docs/deployment.md`.
- **Frontend/product designer:** `README.md` → `docs/ux-space-bridge-minimalist-portal.md` → `packages/ui-bridge`.
- **Agent/tool developer:** `docs/persona-policy.md` → `docs/mcp-tool-contracts.md` → `services/mcp-host`.
- **RAG/document engineer:** `docs/rag-evaluation.md` → `services/knowledge-service` → `local_data/README.md`.
- **Platform/production owner:** `docs/operationalization-gap-analysis.md` → `docs/deployment.md` → `infra/`.

## 1. Executive Summary

**DayPilot Enterprise** is the professional counterpart to **HomePilot**.

HomePilot focuses on local-first personal AI, media generation, voice, memory, and persistent AI identities called **Personas**. DayPilot extends those ideas into a governed workday command center: inbox triage, calendar orchestration, knowledge retrieval, multi-agent operations, approvals, evaluation, and production observability.

The system is designed around one principle:

> **HomePilot creates portable AI identities. DayPilot governs those identities in professional workflows.**

DayPilot is not just a dashboard. It is an operator console for a local-first, cloud-governed, MCP-compatible AI platform. The first release is a complete scaffold containing all major placeholders needed to begin implementation: desktop app, web PWA, mobile PWA, API gateway, agent orchestrator, MCP host, HomePilot persona bridge, knowledge service, voice gateway, model serving adapters, observability, infrastructure, tests, docs, and CI workflows.

**Canonical deployment domain:** `daypilot.ruslanmv.com`  
**Target environments:** Desktop, Web, Mobile PWA  
**Lead architect:** Ruslan Magana Vsevolodovna  
**Primary UX metaphor:** Minimalist tactical **Space Bridge** command center

---

## 2. Product Definition

DayPilot Enterprise is:

> A futuristic local-first AI command center for professional workflows, powered by governed multi-agent orchestration, HomePilot `.hpersona` portability, MCP tool contracts, private RAG memory, and production-grade observability.

It transforms the personal assistant concept into a professional AI operations layer where users can supervise specialized agents such as:

- **Secretary** — email, calendar, follow-ups, meeting preparation, reminders.
- **Coder / GitPilot** — repository inspection, pull request review, coding tasks, release notes.
- **Analyst** — document synthesis, market research, internal knowledge retrieval, reports.
- **Support Operator** — ticket triage, customer history retrieval, escalation suggestions.
- **Voice Operator** — future SIP/WebRTC-enabled live voice agent workflows.

Each agent can be loaded as a DayPilot-native persona or imported from a HomePilot `.hpersona` package.

---

## 3. Why DayPilot Exists

Modern AI products often stop at a chat box. DayPilot starts from the opposite assumption: in a professional environment, AI actions must be **observable, reversible, governed, auditable, and human-approved**.

DayPilot provides:

1. **A tactical operator UI** for seeing all active AI work.
2. **A policy layer** that controls what each persona may do.
3. **An MCP host** that turns external tools into typed contracts.
4. **A HomePilot bridge** that imports portable `.hpersona` identities.
5. **A retrieval layer** that supports private knowledge and citations.
6. **An approval queue** that keeps sensitive actions human-in-the-loop.
7. **An observability layer** for traces, cost, latency, tool calls, and evaluations.

---

## 4. Relationship to HomePilot

The uploaded HomePilot project contains a mature local-first GenAI architecture with the following integration signals detected during scaffold generation:

```json
[
  "README.md local-first GenAI application description",
  "backend/app/personas/export_import.py .hpersona import/export implementation",
  "frontend/src/ui/personaPortability.ts .hpersona frontend API helpers",
  "agentic/integrations/mcp/ MCP communication server scaffolds",
  "docs/PERSONA.md persistent persona primitive documentation",
  ".github/workflows desktop/mobile/container/persona CI workflows"
]
```

HomePilot already provides the core **Persona** primitive:

- A persistent AI identity, not just a prompt.
- Avatar and visual identity.
- Voice and communication readiness.
- Memory and session continuity.
- Portable `.hpersona` export/import packages.
- Tool and MCP dependency manifests.
- Persona-scoped policy concepts.

DayPilot uses these ideas in a professional environment.

### HomePilot → DayPilot Mapping

| HomePilot Concept | DayPilot Enterprise Concept |
|---|---|
| Persona | Governed professional agent package |
| `.hpersona` package | Importable agent bundle with policy review |
| Persona memory | Scoped local-first professional memory |
| Voice mode | Future voice operator and call workflow |
| MCP communication servers | DayPilot MCP tool registry and channel policies |
| Community persona gallery | Enterprise persona registry / installed agents |
| Local-first backend | Local DayPilot runtime with optional cloud gateway |

### `.hpersona` Package Shape

A HomePilot `.hpersona` is a ZIP-like package. DayPilot expects this structure:

```text
persona.hpersona
├── manifest.json
├── preview/card.json
├── blueprint/
│   ├── persona_agent.json
│   ├── persona_appearance.json
│   └── agentic.json
├── dependencies/
│   ├── tools.json
│   ├── mcp_servers.json
│   ├── a2a_agents.json
│   ├── models.json
│   └── suite.json
└── assets/
    ├── avatar_*.png
    └── thumb_*.webp
```

DayPilot imports this package, validates the manifest, extracts the persona identity, inspects dependencies, maps HomePilot tools into DayPilot MCP permissions, and creates a governed local agent record.

### Import Policy

Imported personas are **never fully trusted by default**. DayPilot installs them in a safe state:

```text
INSTALLED_DISABLED → REVIEWED → ENABLED_FOR_READ_ONLY → ENABLED_WITH_APPROVALS → ENABLED_AUTONOMOUS_LIMITED
```

Sensitive actions always require explicit policy permissions:

- Sending email.
- Moving or deleting email.
- Creating or changing calendar events.
- Contacting someone over WhatsApp, Telegram, VoIP, or SMS.
- Writing to Git repositories.
- Executing shell commands.
- Accessing restricted local files.

---

## 5. Core Capabilities

### 5.1 Space Bridge Operator Console

The UI is a minimalist tactical command center. It should feel like operating a mission bridge, not using a generic productivity app.

Core panels:

- **Daily Briefing** — priorities, unread decisions, meetings, risks.
- **Inbox Ops** — triage, summarize, classify, draft, approve.
- **Calendar Ops** — conflicts, briefs, scheduling proposals, deep-work blocks.
- **Active Agents** — running personas, state, tools, permissions, health.
- **Approval Queue** — pending outbound actions requiring user confirmation.
- **Knowledge Inspector** — retrieved documents, citations, confidence, gaps.
- **Trace Console** — LLM calls, tool calls, spans, costs, latency, failures.
- **Persona Registry** — installed HomePilot and DayPilot-native personas.

Visual style:

- Obsidian and midnight backgrounds.
- Cyan information signals.
- Amber warnings.
- Red escalation states.
- Thin grid lines, command palettes, dockable panels.
- Technical typography, compact cards, visible system status.

### 5.2 Autonomous Inbox Management

DayPilot should connect to Gmail, IMAP, Microsoft Graph, or provider-specific APIs through tool adapters.

Target functions:

- Summarize long threads.
- Detect intent and urgency.
- Extract action items.
- Suggest labels and priorities.
- Draft replies in the user’s style.
- Detect follow-up deadlines.
- Escalate sensitive or high-risk emails.
- Require approval before sending or deleting.

### 5.3 Dynamic Calendar Orchestration

DayPilot should help the user manage time like a professional operator.

Target functions:

- Find scheduling conflicts.
- Suggest meeting times.
- Prepare meeting briefs from related email/docs.
- Generate agenda notes.
- Protect deep-work blocks.
- Detect overdue follow-ups from meetings.
- Draft calendar changes but require approval.

### 5.4 Local Knowledge and RAG

The knowledge layer should support private retrieval over:

- Email threads.
- Calendar events.
- PDFs and office documents.
- Notes and local folders.
- Git repositories.
- Meeting transcripts.
- HomePilot persona memory exports.
- `.hpersona` dependency manifests.

The intended retrieval architecture is hybrid:

```text
Document ingestion → chunking → metadata extraction → embeddings
                     ↓
             BM25 / keyword index
                     ↓
Hybrid retrieval → reranking → citation assembly → answer generation → evaluation
```

Evaluation placeholders are included for:

- Context precision.
- Context recall.
- Faithfulness.
- Answer relevance.
- Hallucination risk.
- Retrieval gap reporting.

### 5.5 MCP Tool Orchestration

DayPilot uses MCP-style contracts to expose tools safely to agents.

Example tool namespaces:

```text
daypilot.email.read_inbox
daypilot.email.summarize_thread
daypilot.email.draft_reply
daypilot.email.request_send_approval

daypilot.calendar.search_events
daypilot.calendar.propose_meeting_times
daypilot.calendar.create_event_draft

daypilot.knowledge.search_private_memory
daypilot.knowledge.retrieve_document_context
daypilot.knowledge.evaluate_rag_answer

daypilot.github.inspect_pull_request
daypilot.github.propose_patch
daypilot.github.create_review_comment_draft

daypilot.homepilot.preview_hpersona
daypilot.homepilot.import_hpersona
daypilot.homepilot.install_persona_disabled

daypilot.approvals.request_user_approval
daypilot.observability.record_trace
```

### 5.6 HomePilot Bridge

The HomePilot bridge is one of the most important parts of this scaffold.

It provides:

- `.hpersona` preview.
- Manifest validation.
- Persona identity extraction.
- Tool dependency extraction.
- MCP server dependency extraction.
- Model requirement extraction.
- Safe installation into `local_data/installed_personas`.
- DayPilot policy generation from HomePilot allowed tools.
- A CLI script for previewing imported personas.

The bridge placeholder is located at:

```text
services/mcp-host/daypilot_mcp_host/homepilot_bridge.py
scripts/import_homepilot_persona.py
packages/persona-schema/homepilot-hpersona.schema.json
```

### 5.7 Voice AI Readiness

Voice is intentionally scaffolded but not enabled in the MVP. The future voice architecture is:

```text
SIP / WebRTC / microphone
        ↓
Voice Activity Detection
        ↓
Streaming ASR
        ↓
Agent runtime + tool orchestration
        ↓
Streaming TTS
        ↓
Operator monitor and takeover
```

The first voice workflows should be narrow:

- Meeting brief playback.
- Hands-free daily briefing.
- Support call triage.
- Operator-supervised outbound follow-up.

---

## 6. Architecture

DayPilot is organized into five layers.

### 6.1 Experience Layer

```text
apps/operator-desktop/   Tauri desktop shell
apps/operator-web/       Browser PWA at daypilot.ruslanmv.com
apps/mobile-pwa/         Mobile-first PWA shell
packages/ui-bridge/      Shared Space Bridge UI components
```

### 6.2 Control Plane

```text
services/api-gateway/    Auth, workspace config, API routing
services/orchestrator/   Agent lifecycle, planning, approvals
services/mcp-host/       Tool registry, MCP contracts, HomePilot bridge
```

### 6.3 Intelligence Layer

```text
services/knowledge-service/  RAG ingestion, retrieval, evaluation
services/model-serving/      Local/cloud LLM adapters, routing
services/voice-gateway/      Future ASR/TTS/SIP/WebRTC adapters
```

### 6.4 Data Layer

```text
local_data/sqlite/              Local app database placeholder
local_data/vector_index/        Local vector index placeholder
local_data/documents/           Local document cache placeholder
local_data/installed_personas/  Imported HomePilot/DayPilot personas
local_data/traces/              Local trace export placeholder
```

### 6.5 Observability and Governance

```text
services/observability/     OpenTelemetry/Langfuse-style placeholders
packages/mcp-contracts/     Typed tool contracts and policy metadata
docs/security.md            Security and governance model
docs/rag-evaluation.md      Evaluation strategy
```

---

## 7. Repository Structure

```text
daypilot-enterprise/
├── .github/workflows/
│   ├── ci.yml
│   ├── deploy-gateway.yml
│   └── release-desktop.yml
├── apps/
│   ├── operator-desktop/
│   ├── operator-web/
│   └── mobile-pwa/
├── services/
│   ├── api-gateway/
│   ├── orchestrator/
│   ├── mcp-host/
│   ├── knowledge-service/
│   ├── voice-gateway/
│   ├── model-serving/
│   └── observability/
├── packages/
│   ├── ui-bridge/
│   ├── shared-types/
│   ├── persona-schema/
│   └── mcp-contracts/
├── docs/
│   ├── architecture.md
│   ├── homepilot-integration.md
│   ├── mcp-tool-contracts.md
│   ├── rag-evaluation.md
│   ├── security.md
│   ├── deployment.md
│   └── roadmap.md
├── infra/
│   ├── docker/
│   ├── kubernetes/
│   ├── terraform/
│   ├── cloudflare/
│   └── monitoring/
├── scripts/
├── tests/
├── examples/homepilot-personas/
├── local_data/
├── docker-compose.yml
├── package.json
├── pnpm-workspace.yaml
├── pyproject.toml
├── Makefile
└── README.md
```

---

## 8. Technology Stack

### Frontend

- React
- Vite
- TypeScript
- Tauri for desktop
- PWA for browser and mobile
- Shared Space Bridge UI package

### Backend

- Python 3.11+
- FastAPI
- Pydantic
- SQLite for local metadata
- PostgreSQL placeholder for cloud gateway
- Redis placeholder for jobs and queues

### AI / ML

- Local and cloud LLM adapter placeholders
- RAG pipeline placeholders
- Embedding model adapter placeholders
- Evaluation dataset placeholders
- Future LoRA/QLoRA/DPO training recipes

### MCP / Agents

- MCP-style typed tool contracts
- Persona policy gates
- Human approval queue
- HomePilot `.hpersona` bridge

### Observability

- OpenTelemetry-style trace model
- Langfuse-style LLM traces
- Cost and latency placeholders
- Tool-call audit logs
- Evaluation scorecards

---

## 9. Quick Start

### 9.1 Prerequisites

- Python 3.11+
- Node.js 20+
- pnpm 9+
- Docker and Docker Compose
- Optional: Rust toolchain for Tauri desktop builds

### 9.2 Install

```bash
git clone <your-daypilot-repo-url>
cd daypilot-enterprise
cp .env.example .env
make install
```

### 9.3 Run Local API

```bash
make api
```

API gateway default:

```text
http://localhost:8080
```

Health check:

```bash
curl http://localhost:8080/health
```

### 9.4 Run Web Operator Console

```bash
make web
```

Web console default:

```text
http://localhost:5173
```

### 9.5 Run Docker Stack

```bash
docker compose up --build
```

---

## 10. HomePilot Persona Import

This scaffold includes a sample HomePilot `.hpersona` file when available from the uploaded HomePilot archive:

```text
examples/homepilot-personas/atlas.hpersona
```

Preview it:

```bash
python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --preview
```

Expected output:

```json
{
  "kind": "homepilot.persona",
  "name": "Atlas",
  "role": "Research Assistant",
  "tools": ["web_search", "document_analysis", "citation_manager"],
  "safe_install_state": "INSTALLED_DISABLED"
}
```

Import it into local DayPilot persona storage:

```bash
python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --install
```

Installed personas go to:

```text
local_data/installed_personas/<persona_id>/
```

Each import creates:

```text
persona.json
policy.json
dependencies.json
source_manifest.json
```

---

## 11. Environment Variables

See `.env.example` for the complete placeholder set.

Important values:

```bash
DAYPILOT_ENV=local
DAYPILOT_DOMAIN=daypilot.ruslanmv.com
DAYPILOT_API_PORT=8080
DAYPILOT_LOCAL_DATA=./local_data
DAYPILOT_REQUIRE_APPROVALS=true
DAYPILOT_HOMEPILOT_IMPORTS_ENABLED=true
DAYPILOT_MCP_WRITE_ENABLED=false
DAYPILOT_MCP_DRY_RUN=true
```

---

## 12. Security Model

DayPilot treats every imported persona, retrieved document, external tool, and model output as untrusted until policy allows it.

Core safety principles:

1. **Least privilege** — each persona gets minimum tool permissions.
2. **Human approval** — high-impact actions require approval.
3. **Auditability** — all tool calls generate trace events.
4. **Local-first privacy** — private data stays local by default.
5. **Prompt injection resistance** — retrieved content cannot silently grant permissions.
6. **Dry-run by default** — mutating MCP actions start disabled.
7. **Explicit consent** — outbound communication tools require consent.

---

## 13. Development Roadmap

### Phase 1 — Foundation MVP

- Tauri shell placeholder.
- React Space Bridge UI placeholder.
- FastAPI gateway with health endpoints.
- HomePilot `.hpersona` parser.
- Local persona registry.
- MCP contract registry placeholders.
- Approval queue model.
- Documentation and CI.

### Phase 2 — Inbox and Calendar

- Gmail/Microsoft/IMAP connectors.
- Email triage agent.
- Calendar conflict detector.
- Draft reply and schedule proposal workflows.
- Approval queue UI.

### Phase 3 — Knowledge and RAG

- Document ingestion.
- Local vector index.
- Hybrid retrieval.
- Citation inspector.
- RAG evaluation scorecards.

### Phase 4 — Agent Governance

- Persona permissions UI.
- MCP allowlists.
- Tool-call replay.
- Audit log export.
- Policy simulation.

### Phase 5 — Observability and MLOps

- OpenTelemetry traces.
- LLM trace dashboards.
- Cost tracking.
- Evaluation datasets.
- Model comparison and release gates.

### Phase 6 — Voice AI

- Voice activity detection.
- Streaming ASR/TTS adapters.
- SIP/WebRTC gateway.
- Live transcript inspector.
- Operator takeover.

---

## 14. Success Metrics

### Product Metrics

- Time saved per day.
- Email triage accuracy.
- Draft acceptance rate.
- Meeting preparation usefulness.
- Missed follow-up reduction.
- Approval queue completion rate.

### AI Quality Metrics

- Retrieval precision.
- Retrieval recall.
- Faithfulness.
- Hallucination rate.
- Tool-call success rate.
- Agent task completion rate.

### Reliability Metrics

- P95 API latency.
- Tool-call failure rate.
- Background job failure rate.
- Sync failure rate.
- Model timeout rate.
- Cost per completed task.

### Safety Metrics

- Unauthorized tool attempts blocked.
- PII redaction events.
- Prompt injection detections.
- User escalations.
- Approval overrides.

---

## 15. Design Principle

DayPilot may let agents think, retrieve, draft, and propose.

But DayPilot governs execution.

> The model may propose actions, but the platform decides what is allowed.

---

## 16. Current Scaffold Status

This ZIP is a **project bootstrap scaffold**, not a production release. It intentionally contains placeholders so the repository can grow cleanly into the full DayPilot platform.

Included now:

- Complete README.
- Monorepo layout.
- Web, desktop, and mobile app placeholders.
- FastAPI service placeholders.
- MCP host and HomePilot bridge placeholders.
- `.hpersona` parser utility.
- Persona schema placeholder.
- Docs skeleton.
- Docker Compose placeholder.
- CI workflow placeholders.
- Local data directories.

Next implementation target:

> Build the HomePilot `.hpersona` import flow end-to-end, then connect imported personas to the DayPilot operator console and approval queue.


## Operationalization Pack v0.2

This ZIP revision includes the missing production-readiness foundations identified during the workspace review:

- Complete per-service Dockerfiles in `infra/docker/`.
- Multi-service `docker-compose.yml` with Postgres, Redis, Qdrant, and optional Prometheus.
- Kubernetes Kustomize manifests in `infra/kubernetes/`.
- Terraform AWS bootstrap files in `infra/terraform/`.
- Alembic schema controls plus SQLAlchemy models for users, personas, calendars, inboxes, documents, document chunks, and audit logs.
- FastAPI runtime surfaces for orchestrator, MCP host, knowledge-service, model-serving, voice-gateway, and observability.
- Shared UI bridge atomic components for consistent operator screens.
- Expanded tests for orchestration, persistence, model routing, voice, traces, and API health.

### New local validation commands

```bash
python scripts/init_db.py
alembic upgrade head
python -m pytest -q
```

### Full service stack

```bash
docker compose up --build
```

Runtime-heavy components can be enabled separately:

```bash
docker compose --profile runtime --profile observability up --build
```

For a line-by-line operationalization summary, see `docs/operationalization-gap-analysis.md`.


## V3 Premium Minimalist Portal Upgrade

This revision adds the production UI/UX blueprint for the DayPilot Premium Minimalist Portal. The visual direction is now intentionally closer to a calm Apple-style command surface than a dense operations dashboard:

- Chat-first Strategic Feed for natural-language scheduling and delegation.
- Clickable Strategy Blocks for team meetings, deep-work windows, and AI-generated work plans.
- Day Horizon and Week Horizon calendar views that show how AI distributes work across time.
- Operational Ledger that separates Commander manual assignments from autonomous `.hpersona` processes.
- Right-edge context drawer for email/source/GitPilot/RAG telemetry without disruptive modals.
- Obsidian monochrome token system using Apple Blue, Cyber Cyan, System Purple, and Alert Orange only as state telemetry.

Key files:

- `docs/ux-space-bridge-minimalist-portal.md` — ASCII wireframes and permanent UI rules.
- `packages/ui-bridge/src/minimalPortal.tsx` — React implementation of the chat/calendar/tasks portal.
- `packages/ui-bridge/src/spaceBridgeData.ts` — shared sample state for messages and work blocks.
- `packages/ui-bridge/src/space-bridge.css` — minimalist visual token system and layout styles.
- `examples/ui/daypilot-premium-minimalist-portal.html` — standalone no-build HTML prototype.
