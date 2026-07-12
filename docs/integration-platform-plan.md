# DayPilot Integration Platform — Batch Roadmap (additive, non-destructive)

This plan decomposes the five-phase integration feature into implementable,
dependency-ordered batches (`I0`–`I10`) in the same style as the
[production plan](production-plan.md). Every batch is **additive** (new modules,
tables, routes, and UI panels — nothing existing is removed or rewritten) and
**non-destructive** (opt-in per workspace, draft/dry-run by default, every
write/send/destructive action gated by the existing Approval Center; the AI never
touches a provider or MCP server directly).

> Guiding principle: **build one complete, secure integration workflow before
> building a marketplace.** The minimum useful product is Phase 1 + Phase 2
> (`I0`–`I3`). Phase 3 (`I4`–`I5`) makes it scalable; Phases 4–5 (`I6`–`I10`)
> follow only after the first integration is reliable and actively used.

> **Status: all batches (I0–I10) implemented and tested.** Each batch below
> carries a per-batch status note. The remaining production hardening (live OAuth
> callbacks + Events API signature verification, a persistent per-workspace
> catalog/enablement store, and unifying MCP under the exact same provider
> registry) is called out inline where relevant.

---

## 1. Reuse map — what already exists

These batches wire into DayPilot's existing trust layer instead of duplicating it:

| Need | Existing foundation to reuse |
|---|---|
| Approval workflow | Approval Center (`services/orchestrator/daypilot_orchestrator/approvals/center.py`) + `Approval` model |
| Audit log | `Event` model + `_audit(...)` emitters + `/v1/.../audit/export` |
| Secure credentials | `security/secrets.py` (`redact()`, env-injected backend) — never DB/logs/prompts |
| Permissions / roles | `services/api-gateway/app/{auth.py,rbac.py}` (`require_role`) |
| Event queue / durable jobs | `jobs/{queue.py,worker.py}` (retries, backoff, dead-letter) |
| MCP servers & tool registry | MCP host (`services/mcp-host/daypilot_mcp_host/{registry.py,server.py}`) |
| Injection defense | `security/injection_guard.py` (screen external content before it reaches tools) |
| Live UI updates | SSE Today Context event stream |
| Draft-and-approve UX pattern | Email Sentinel (`email/`) — Slack mirrors it exactly |
| Provider health pattern | `daypilot_models/provider_health.py` |
| Integrations UI surface | Settings → Integrations (`packages/ui-bridge/src/settings/settingsData.ts`, display-only today) |

**Non-destructive guarantees (hold for every batch):**
1. Integrations are opt-in per workspace and default **disconnected**.
2. Default mode is **draft-only / dry-run**; no auto-send, no auto-write.
3. Every send / write / destructive tool call passes through the Approval Center.
4. The AI never calls a provider or MCP server directly — always via the tool router → policy → approval → client path.
5. Credentials live in the secrets backend, redacted from logs/traces/prompts.
6. Disconnect and token revocation are always available; disconnect purges cached tokens.
7. The existing Settings → Integrations UI/UX is preserved — it becomes backed by real connection records without changing its shape.

---

## 2. Batch roadmap overview

| Phase | Batches | Outcome |
|---|---|---|
| **1 — Foundation** | `I0`, `I1` | Integration Gateway, connection records, secure creds, permission model, approval + audit + event-queue wiring, health, live Integrations page. One provider proves connect → read → write-with-approval → audit → failure. |
| **2 — First useful integration (Slack)** | `I2`, `I3` | OAuth connect, inbound mentions/DMs → notification → AI draft → approve/edit/reject → send, with automation rules. Draft-only by default. |
| **3 — MCP support** | `I4`, `I5` | Attach remote (Streamable HTTP) / local (STDIO) MCP servers, discover + classify tools, govern execution through the policy layer. |
| **4 — More providers + unified notifications** | `I6`, `I7`, `I8` | Normalized `IntegrationEvent`, one Notification Center, ≥3 provider types, per-integration rules, predefined cross-integration workflows. |
| **5 — Private platform** | `I9`, `I10` | Manifests, curated catalog, admin controls, SDK, conformance/certification, install/update/disable out-of-core. |

Shared contracts land in `packages/mcp-contracts` (or a new
`packages/integration-contracts`) and `packages/shared-types`; backend lives in a
new `services/orchestrator/daypilot_orchestrator/integrations/` package plus
gateway routers under `services/api-gateway/app/routers/integrations*.py`.

---

## Batch I0 — Integration Gateway, connection records, secure credentials, health

> **Status: landed.** Backend foundation implemented and tested
> (`services/orchestrator/daypilot_orchestrator/integrations/`, migration 0005,
> `services/api-gateway/app/routers/integrations.py`, shared TS contracts, and
> `tests/test_integrations_gateway.py`). All six Phase-1 completion criteria pass.

**Goal:** the minimum architecture every future integration uses — a provider
interface, connection records, safe credential storage, and health status — with
the existing Settings → Integrations page made live (read-only actions only).
**Depends on:** B1 (data model), B11 (secrets, auth/RBAC). Additive only.

**Files:** new `services/orchestrator/daypilot_orchestrator/integrations/{__init__.py,gateway.py,provider.py,registry.py,health.py,credentials.py}`; new `IntegrationConnection` table (migration 0005); `services/api-gateway/app/routers/integrations.py`; shared `packages/shared-types` + `packages/integration-contracts`; UI `packages/ui-bridge/src/integrations/IntegrationsPanel.tsx` (replaces the static Integrations list in place).

**Work items**
1. Define the provider contract (TS + Python parity):
   ```ts
   interface IntegrationProvider {
     connect(): Promise<void>;
     disconnect(): Promise<void>;
     listCapabilities(): Promise<Capability[]>;
     execute(action: string, input: unknown): Promise<unknown>;
     getHealth(): Promise<IntegrationHealth>;
   }
   ```
   DayPilot never learns whether a provider is native-API or MCP internally.
2. `IntegrationConnection` record (small first model), per workspace:
   ```ts
   type IntegrationConnection = {
     id: string; workspaceId: string; provider: string;
     status: "connected" | "error" | "expired";
     authType: "oauth" | "api_key" | "mcp";
     capabilities: string[];
   };
   ```
3. Integration Gateway: registry of installed providers, resolve `provider → IntegrationProvider`, and a single `execute()` entry the rest of DayPilot calls (no direct provider access elsewhere).
4. Secure credential storage: store tokens/keys only in the secrets backend keyed by connection id; the DB holds references, never secrets; `redact()` covers all integration logs.
5. Health: `getHealth()` per connection surfaced as `connected | error | expired`, on the same pattern as provider health, refreshed on a schedule + on demand.
6. Live Integrations page (preserve the current layout): list providers with **Not connected / Connected**, and for connected ones show status, granted capabilities, last successful activity, and **Disconnect**.

**Acceptance:** a workspace can create/list/disconnect a connection; credentials never appear in DB rows, logs, or API responses; the Integrations page reflects real connection state; an induced auth failure flips status to `error` and shows in the UI.
**Satisfies:** Phase 1 items 1–2, 6 (connect, store safely, detect/display failure).

---

## Batch I1 — Permission model, approval + audit wiring, event queue, reference provider

> **Status: landed.** Permission model (`permissions.py`), Approval-gated writes
> via a durable `Job` + Approval Center, full audit trail, the built-in
> `reference` provider, **and** the autonomous worker path (`worker.py`:
> `promote_approved_actions` + `run_pending`) that performs approved jobs without
> a manual call. The live Integrations page (`IntegrationsPanel.tsx`) shows
> status, granted capabilities, last activity, and Connect/Disconnect. All
> Phase-1 completion criteria pass.

**Goal:** complete the Phase-1 loop — read and write capabilities with a
permission model, writes gated by the Approval Center, every action audited, and a
basic event queue — proven by one reference provider.
**Depends on:** I0; reuses Approval Center, `Event` audit, `jobs/` queue, RBAC.

**Files:** `integrations/{permissions.py,actions.py,events.py}`; extend `approvals/center.py` with an `integration.execute` approval kind; `jobs/` producer for integration events; a `integrations/providers/reference.py` (a safe echo/mock provider) + tests.

**Work items**
1. Capability + permission model: each capability is classified `read | write | destructive`; a per-connection permission grant maps capabilities to `allowed | approval_required | blocked` (safe defaults: reads `allowed`, writes/destructive `approval_required`).
2. Execution path: `Gateway.execute(connectionId, action, input)` → RBAC check → permission check → **read runs immediately**; **write/destructive opens an Approval Center item** (human-readable summary, provider, capability, input preview, triggering policy) and only executes on approval.
3. Audit: every step (`connect`, `read`, `write.requested`, `write.approved`, `write.executed`, `error`) emits an `Event`/audit record, exportable via the existing audit export.
4. Basic event queue: integration-originated events enqueue on the durable `jobs/` queue (retries/backoff/dead-letter reused); a worker fans them into the Today/notification stream.
5. Reference provider: a built-in provider exposing one read (`echo.read`) and one write (`echo.write`) capability to exercise the full loop offline in CI.

**Acceptance (Phase 1 complete):** with the reference provider a workspace can (1) connect, (2) store creds safely, (3) execute a read, (4) execute a write **only after approval**, (5) find every step in the audit log, (6) see a failure surfaced. No marketplace, SDK, ratings, billing, or auto-install exists yet.
**Satisfies:** Phase 1 items 3–5 and the full Phase-1 completion criteria.

---

## Batch I2 — Slack connect (OAuth) + inbound events + notification

> **Status: landed (core).** `SlackProvider` (`providers/slack/adapter.py`) with
> `chat.read`/`chat.send` capabilities and an injectable transport; inbound events
> normalized and turned into notifications with content screened by the injection
> guard (`integrations/slack.py`). Remaining for a later pass: the live OAuth
> callback route + Events API signature verification (tests use a mock transport).

**Goal:** prove integrations create real value — connect a Slack workspace and turn
mentions/DMs into DayPilot notifications.
**Depends on:** I0, I1.

**Files:** `integrations/providers/slack/{__init__.py,oauth.py,adapter.py,events.py}`; gateway callback route `app/routers/integrations_slack.py`; UI Slack connect card + notification surface.

**Work items**
1. OAuth connect flow (authorization-code) storing the bot/user tokens in the secrets backend; connection `authType: "oauth"`, capabilities discovered from granted scopes.
2. Inbound events: receive bot direct messages and app mentions (Events API/socket); verify signatures; screen content through `injection_guard` before it reaches any AI step.
3. Read an authorized thread (read capability) on demand to build reply context.
4. Normalize each inbound event to the internal event shape and create a **DayPilot notification** (e.g., "Client Alpha asked about the revised deadline — AI reply ready").

**Acceptance:** connecting a Slack workspace persists a `connected` connection; a mention produces a notification with a **Review reply** affordance; thread reads are audited; malformed/injection content is flagged, not acted on.
**Satisfies:** Phase 2 items — event enters DayPilot, creates a notification (and sets up the draft in I3).

---

## Batch I3 — Slack draft → approve → send loop + automation rules

> **Status: landed.** Draft-only by default (`slack.ingest_event` → notification +
> draft, never sends); `slack.request_send` routes through the gateway write path
> so a send opens an approval and the worker posts it only after approval;
> automation rules (`automation.py`: allowed channels/types, business hours,
> draft-only/auto-ack, rate-cap). `tests/test_integration_slack.py` proves the
> full loop, the skip rule, and injection flagging.

**Goal:** the first complete integration loop — AI draft, human approval, approved
send — with minimal automation controls. **Draft-only by default.**
**Depends on:** I2; reuses the Email Sentinel draft-and-approve pattern + Approval Center.

**Files:** `integrations/providers/slack/reply.py`; `integrations/automation.py` (rules); Approval view for Slack replies in the UI (mirrors the email Add-to-composer pattern).

**Work items**
1. AI reply draft: generate a suggested response from the thread context via the connector; **never send automatically**.
2. Approval view: `[Edit] [Approve and send] [Reject]` on the draft; edit is free-text; approve triggers the send capability (a write → Approval-gated); reject records the reason.
3. Send the approved response through the Slack adapter's write capability; record the returned message id.
4. Automation rules (basic only): allowed channels, allowed message types, business hours, draft-only vs. automatic acknowledgement, and a max-replies-per-hour rate limit (reuse the queue's backpressure). Defaults: draft-only, no channels auto-enabled.
5. Full audit trail across mention → notification → draft → approval → send.

**Acceptance (Phase 2 complete):** a new Slack event can enter DayPilot, create a notification, trigger an AI draft, require approval, send on approval, and record every step; with default settings nothing is ever sent without a human approving.
**Satisfies:** Phase 2 completion criteria + minimal automation rules.

---

## Batch I4 — Generic MCP connection support (remote + local)

> **Status: landed.** `MCPConnection` model + migration 0006; client transports
> (`mcp/client.py`: `StreamableHttpClient`, `StdioClient`, both injectable);
> attach + tool discovery + enable/disable + health (`mcp/service.py`); router
> `/v1/integrations/mcp`. Tools start disabled (opt-in).

**Goal:** attach external MCP servers without changing the core — remote
(Streamable HTTP) and local (STDIO), with tool discovery and health.
**Depends on:** I0; extends the existing MCP host.

**Files:** extend `services/mcp-host/daypilot_mcp_host/{registry.py,server.py}` with transports; `integrations/mcp/{connection.py,client.py,transports.py}`; `MCPConnection` table (migration 0006); UI "Add MCP Server" form + tool list.

**Work items**
1. Add remote MCP server via **Streamable HTTP** (`endpoint`) and local via **STDIO** (`command`); persist an `MCPConnection`:
   ```ts
   type MCPConnection = {
     id: string; name: string;
     transport: "stdio" | "streamable_http";
     endpoint?: string; command?: string;
     status: "connected" | "unavailable" | "error";
     enabledTools: string[];
   };
   ```
2. Discover available tools; display tool name + description; enable/disable individual tools (disabled by default).
3. Health monitoring per server; timeouts and error handling on every call.
4. Register the MCP server as an `IntegrationProvider` (`authType: "mcp"`) so it flows through the same Gateway — DayPilot doesn't care that it's MCP internally.

**Acceptance:** an admin can add a remote and a local MCP server, see discovered tools with descriptions, toggle individual tools, and observe health/timeout handling.

---

## Batch I5 — MCP tool governance: classification, policy routing, approvals

> **Status: landed.** Auto-classification (`mcp/classification.py`) with
> tokenized name heuristics + MCP annotation hints and per-tool admin override;
> `execute_tool` enforces AI → router → policy → approval → client → server (reads
> run inline, writes/destructive open an approval + durable job, performed only
> after approval). `tests/test_integration_mcp.py` proves all seven Phase-3
> completion criteria.

**Goal:** every MCP tool call flows through DayPilot's policy layer — never directly
from the AI — with automatic classification an admin can override.
**Depends on:** I4, I1 (permissions/approvals), B11 (RBAC/injection).

**Files:** `integrations/mcp/classification.py`; `integrations/mcp/router.py` (the tool router); policy wiring in `approvals/center.py`.

**Work items**
1. Auto-classify each tool `read | write | destructive` (heuristics on name/schema/annotations); **administrators can override** the classification per tool.
2. Enforce the execution path exactly:
   ```text
   AI request → DayPilot tool router → policy check → approval check → MCP client → MCP server
   ```
   The AI can only emit a tool *request*; it can never open an MCP client itself.
3. Permission mapping: read tools `allowed` (or `approval_required` by policy), write/destructive tools `approval_required`, with the Approval Center showing the tool, arguments preview, and classification.
4. Timeouts, error surfacing, and audit records for every tool execution and result.

**Acceptance (Phase 3 complete):** an admin can attach a server, inspect tools, enable selected tools, assign permissions, let AI use an allowed read tool, require approval for a write tool, and view the result + audit record. DayPilot is MCP-ready without being a marketplace.
**Satisfies:** Phase 3 completion criteria + the required security rule.

---

## Batch I6 — Normalized events + Unified Notification Center

> **Status: landed.** `integrations/notifications.py`: one `IntegrationEvent`
> shape (`normalize`), a notification store on the Event stream, severity
> grouping (approval/attention/info), per-integration delivery rules, and
> `GET /v1/notifications` + `/summary`.

**Goal:** one event format and one place to see everything, with per-integration
notification rules.
**Depends on:** I1, I3.

**Files:** `integrations/events.py` (normalizer); UI `packages/ui-bridge/src/notifications/NotificationCenter.tsx`; notification-rules settings section.

**Work items**
1. Normalize all provider activity to one shape:
   ```ts
   type IntegrationEvent = {
     id: string; provider: string; connectionId: string;
     type: "message.received" | "mention.created" | "comment.created"
         | "task.updated" | "approval.required" | "connection.error";
     title: string; summary: string; occurredAt: string;
     severity: "info" | "attention" | "approval";
   };
   ```
2. Unified Notification Center grouping by severity (**Approval / Attention / Information**) with per-item actions (Review / Open / View); reuse the SSE stream for live updates.
3. Per-integration notification rules (Immediate / Daily summary / Important only / Off), e.g., Slack mentions Immediate, channel messages Daily summary, GitHub failures Immediate.

**Acceptance:** events from multiple providers appear in one center, grouped by severity, honoring per-integration rules; the same approval model drives every "approval"-severity item.

---

## Batch I7 — Additional providers behind one interface (≥3 types)

> **Status: landed.** GitHub and Google Calendar providers
> (`providers/extra.py`) added behind `IntegrationProvider` with injectable
> transports, giving three real provider types (Slack, GitHub, Calendar) that
> reuse the gateway, permission model, approvals, audit, and notifications.

**Goal:** expand carefully — add providers without a bespoke workflow each.
**Depends on:** I0–I1, I6.

**Files:** `integrations/providers/{github,microsoft365,google,notion,jira,crm}/adapter.py` (start with GitHub + one of Microsoft 365/Google Workspace + one of Notion/Jira/CRM).

**Work items**
1. Implement each provider against `IntegrationProvider`, mapping native APIs to capabilities + normalized `IntegrationEvent`s. No provider-specific approval or notification logic.
2. Reuse the Gateway, permission model, Approval Center, audit, and Notification Center for all of them.
3. Document required scopes per provider; reads `allowed`, writes `approval_required` by default.

**Acceptance:** at least three provider types connect, normalize their events, and route sensitive actions through the same approval model.

---

## Batch I8 — Predefined cross-integration workflows

> **Status: landed.** `integrations/workflows.py`: opt-in predefined workflows
> (Slack message → task, GitHub failure → notify, Email request → follow-up) with
> `GET /v1/workflows` + `POST /v1/workflows/{id}/run`. Outbound steps stay
> approval-gated via the gateway. `tests/test_integration_phase4.py` proves all
> Phase-4 completion criteria.

**Goal:** simple, safe cross-provider automations — no visual builder yet.
**Depends on:** I6, I7.

**Files:** `integrations/workflows/{registry.py,handlers.py}`; workflow settings UI (toggle + simple options).

**Work items**
1. Ship a small set of predefined workflows with simple settings:
   - Slack message → create DayPilot task
   - GitHub failure → notify an engineering channel
   - Email request → create a project follow-up
   - LinkedIn Page comment → prepare an **approved** response (draft-only)
2. Each workflow is opt-in, scoped to a connection/channel, and any outbound step is approval-gated. No arbitrary automation graph.

**Acceptance (Phase 4 complete):** ≥3 provider types connected, events normalized into one center, the same approval model applied everywhere, ≥1 cross-integration workflow runs, and users can configure notification preferences.
**Satisfies:** Phase 4 completion criteria.

---

## Batch I9 — Manifests, curated catalog, admin controls, versioning

> **Status: landed.** `integrations/manifest.py`: `IntegrationManifest` +
> `validate_manifest` (semver, transport, risk, capabilities), a curated catalog
> with tiers (verified/certified/private/experimental) seeded with real entries,
> and `register_manifest`/`list_catalog`/`set_certified`. Router `/v1/catalog`.

**Goal:** turn the internal system into a controlled (curated, not public) platform.
**Depends on:** Phases 1–4 stable.

**Files:** `integrations/manifest.py` (schema + validation); catalog service + UI `IntegrationCatalog.tsx`; admin controls in settings.

**Work items**
1. Integration manifest every integration declares:
   ```json
   {
     "id": "company-crm", "name": "Company CRM", "version": "1.2.0",
     "publisher": "Internal Platform Team", "transport": "streamable-http",
     "capabilities": ["customer.search","customer.read","customer.update"],
     "events": ["customer.created","customer.updated"], "risk": "medium"
   }
   ```
2. Curated catalog with tiers: **Verified / DayPilot Certified / Private / Experimental**; workspace administrators control which are enabled.
3. Security classification per integration; version management + compatibility checks; private enterprise integrations stay workspace-scoped.

**Acceptance:** admins browse a curated catalog, see risk/tier/version, and enable integrations per workspace via manifest.

---

## Batch I10 — Integration SDK + conformance/certification + lifecycle

> **Status: landed.** `integrations/sdk.py` re-exports the provider contract,
> manifest, capability vocabulary, and conformance runner for out-of-core
> builders (with TS parity in `shared-types`: `IntegrationManifest`,
> `DayPilotIntegration`, `ConformanceResult`). `integrations/certification.py`
> runs the check suite (manifest valid, capabilities classified + match manifest,
> auth/health/disconnect work, no credential leak); `/v1/catalog/install` +
> `/{id}/certify` drive the install→certify lifecycle. `tests/test_integration_phase5.py`
> proves the Phase-5 criteria.

**Goal:** let internal/third-party teams build integrations **outside** the core repo
and have DayPilot install, test, classify, and manage them without core changes.
**Depends on:** I9.

**Files:** `packages/integration-sdk/` (published SDK); `integrations/certification/{checks.py,runner.py}`; install/update/disable lifecycle in the gateway.

**Work items**
1. SDK surface for integration developers:
   ```ts
   export interface DayPilotIntegration {
     manifest: IntegrationManifest;
     connect(): Promise<void>;
     capabilities(): Promise<Capability[]>;
     execute(action: string, input: unknown): Promise<unknown>;
     health(): Promise<HealthResult>;
   }
   ```
   Helpers for MCP connection, event adapter, auth config, capability mapping, default permissions, health checks, and UI metadata.
2. Automated **certification checks** run before enable: auth works, tool schemas valid, read/write tools classified, scopes documented, timeouts enforced, credentials not exposed, audit events generated, disconnect + revocation work.
3. Lifecycle: install via manifest, run conformance, classify, admin-approve, user-connect, and update/disable without touching the core application.

**Acceptance (Phase 5 complete):** a team can build an integration outside the core repo, install it via manifest, have DayPilot test/classify it, admins approve it, users connect it, and DayPilot update/disable it without core changes.
**Satisfies:** Phase 5 completion criteria.

---

## 3. Suggested execution order

```text
I0 → I1            Foundation (minimum viable, Phase 1)
I2 → I3            Slack: the first complete loop (Phase 2)  ← minimum useful product = I0–I3
I4 → I5            Generic MCP support (Phase 3)
I6 → I7 → I8       More providers + unified notifications (Phase 4)
I9 → I10           Private integration platform (Phase 5)
```

Stop-and-use points: after **I3** DayPilot has one complete, secure, non-destructive
integration workflow; after **I5** it is MCP-ready; Phases 4–5 proceed only once the
first integrations are reliable and in active use.

## 4. What is explicitly out of scope early

Per the source spec, do **not** build (until the phase that introduces them): a
public marketplace, public SDK, ratings, billing, or automatic installation (all
Phase 5, curated/private first); a visual automation builder (Phase 4 uses
predefined workflows); and automatic replies by default (Phase 2 is draft-only).
