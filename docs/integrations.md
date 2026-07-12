# Integrations — using the Integration Gateway

DayPilot connects external providers (Slack, GitHub, Google Calendar) and **MCP
servers** through one governed **Integration Gateway**. This guide is the
practical companion to the [integration platform plan](integration-platform-plan.md)
(batches I0–I10). For the design rationale and roadmap, read that; for how to use
it, read this.

## The governance model (read this first)

One rule underlies everything:

> **Reads run immediately. Every write, send, or destructive action is
> approval-gated, audited, and reversible. The AI can only *request* a tool — it
> never calls a provider or MCP server directly.**

- Capabilities are classified `read` / `write` / `destructive`. Default
  permission: reads `allowed`, writes/destructive `approval_required`
  (admin-overridable per capability).
- A write enqueues a **durable job** and opens an **Approval Center** item; it
  runs only after approval (a worker performs it, or the approver's client calls
  the `.../perform` endpoint).
- **Credentials** live in the secrets backend keyed by connection id — never in
  the database, logs, traces, or prompts. Disconnect revokes them.
- Every step (`connect`, `read.executed`, `write.requested`, `write.executed`,
  `disconnect`) is written to the audit log and the SSE event stream.

Everything is **opt-in per workspace** and additive — connecting an integration
never changes existing behaviour.

## Connect a provider

```bash
# List providers and existing connections
curl localhost:8080/v1/integrations

# Connect (credentials go to the secrets backend, never the DB)
curl -X POST localhost:8080/v1/integrations/connect \
  -H 'content-type: application/json' \
  -d '{"provider":"slack","credentials":{"bot_token":"xoxb-…"}}'

# Inspect capabilities (with effective permission), refresh health, disconnect
curl localhost:8080/v1/integrations/<id>/capabilities
curl -X POST localhost:8080/v1/integrations/<id>/health
curl -X POST localhost:8080/v1/integrations/<id>/disconnect
```

### Execute an action

```bash
# A read runs immediately
curl -X POST localhost:8080/v1/integrations/<id>/execute \
  -d '{"action":"repo.read","input":{"repo":"ruslanmv/DayPilot"}}'
# → {"status":"executed","result":{…}}

# A write opens an approval + a durable job (nothing runs yet)
curl -X POST localhost:8080/v1/integrations/<id>/execute \
  -d '{"action":"pr.create","input":{"repo":"ruslanmv/DayPilot","title":"…","head":"feat"}}'
# → {"status":"approval_required","approvalId":"…","jobId":"…"}

# Approve in the Approval Center, then it executes (worker, or perform):
curl -X POST localhost:8080/v1/approvals/<approvalId>/decide -d '{"decision":"approve"}'
curl -X POST localhost:8080/v1/integrations/actions/<jobId>/perform
```

**Built-in providers:** `slack`, `github`, `calendar` (Google Calendar), and a
`reference` provider for testing. Adding a provider is a self-contained adapter
implementing the `IntegrationProvider` interface — no new approval, notification,
or gateway logic.

### Slack, end to end (draft-only by default)

`mention/DM → notification → AI draft → approve/edit/reject → send`. Inbound
content is screened by the injection guard before any AI step; a reply is only a
draft until you send it, and the send is an approval-gated `chat.send`. Automation
rules (allowed channels/types, business hours, draft-only vs auto-ack, per-hour
cap) live in `integrations/automation.py`.

## Attach an MCP server

```bash
# Add a remote (Streamable HTTP) or local (STDIO) server
curl -X POST localhost:8080/v1/integrations/mcp/add \
  -d '{"name":"Internal CRM","transport":"streamable_http","endpoint":"https://mcp.company.com/mcp"}'

# Inspect discovered tools (auto-classified; all start disabled)
curl localhost:8080/v1/integrations/mcp/<id>/tools

# Enable a tool; optionally override its classification
curl -X POST localhost:8080/v1/integrations/mcp/<id>/tools/search_customers/enable -d '{"enabled":true}'
curl -X POST localhost:8080/v1/integrations/mcp/<id>/tools/search_customers/classify -d '{"kind":"write"}'

# Execute — read runs now; write opens an approval, then perform after approval
curl -X POST localhost:8080/v1/integrations/mcp/<id>/execute -d '{"tool":"search_customers","arguments":{"q":"acme"}}'
curl -X POST localhost:8080/v1/integrations/mcp/actions/<jobId>/perform
```

The required execution path is enforced:

```text
AI request → tool router → policy check → approval check → MCP client → server
```

Tools are auto-classified from their name (and MCP `readOnlyHint`/`destructiveHint`
annotations), and an administrator can override any classification.

## Unified notifications & workflows

All providers normalize to one `IntegrationEvent` shape and one center, grouped by
severity (`approval` / `attention` / `info`), with per-integration delivery rules.

```bash
curl localhost:8080/v1/notifications            # list + summary (optional ?severity=approval)
curl localhost:8080/v1/notifications/summary    # counts by severity

# Predefined, opt-in cross-integration workflows (no visual builder)
curl localhost:8080/v1/workflows
curl -X POST localhost:8080/v1/workflows/slack_message_to_task/run \
  -d '{"event":{"summary":"Client asks about the deadline"}}'
```

Shipped workflows: `slack_message_to_task`, `github_failure_to_notify`,
`email_request_to_followup`. Outbound steps stay approval-gated.

## Private catalog, manifests & the SDK

A curated (not public) catalog with tiers — **verified / certified / private /
experimental**. Every integration declares a manifest; DayPilot certifies it
before it can be enabled.

```bash
curl localhost:8080/v1/catalog                  # browse (optional ?tier=verified)
curl -X POST localhost:8080/v1/catalog/install  -d '{"manifest":{…},"tier":"experimental"}'
curl -X POST localhost:8080/v1/catalog/<id>/certify
```

**Manifest** (declared by every integration):

```json
{
  "id": "company-crm", "name": "Company CRM", "version": "1.2.0",
  "publisher": "Internal Platform Team", "transport": "streamable-http",
  "capabilities": ["customer.search", "customer.read", "customer.update"],
  "events": ["customer.created", "customer.updated"], "risk": "medium"
}
```

**SDK.** Build an integration **outside** the core repo against
`daypilot_orchestrator.integrations.sdk` (Python) or the `DayPilotIntegration`
contract in `@daypilot/shared-types` (TypeScript). Self-test with the conformance
runner before submitting:

```python
from daypilot_orchestrator.integrations import sdk
report = sdk.run_conformance(my_manifest, MyIntegration())
assert report["passed"]  # manifest valid, capabilities classified + match,
                         # auth/health/disconnect work, no credential leak
```

## API surface (summary)

| Area | Endpoints |
|---|---|
| Gateway | `GET /v1/integrations` · `POST /connect` · `GET /{id}` · `/{id}/capabilities` · `POST /{id}/health` · `/{id}/disconnect` · `/{id}/execute` · `/actions/{jobId}/perform` |
| MCP | `GET /v1/integrations/mcp` · `POST /mcp/add` · `GET /mcp/{id}/tools` · `POST /mcp/{id}/tools/{tool}/enable` · `/classify` · `/mcp/{id}/execute` · `/mcp/actions/{jobId}/perform` |
| Notifications | `GET /v1/notifications` · `GET /v1/notifications/summary` |
| Workflows | `GET /v1/workflows` · `POST /v1/workflows/{id}/run` |
| Catalog | `GET /v1/catalog` · `POST /v1/catalog/install` · `POST /v1/catalog/{id}/certify` |

## Where the code lives

- Gateway + providers + governance: `services/orchestrator/daypilot_orchestrator/integrations/`
  (`gateway`/`service`, `provider`, `permissions`, `credentials`, `registry`,
  `providers/`, `slack.py`, `automation.py`, `notifications.py`, `workflows.py`,
  `mcp/`, `manifest.py`, `certification.py`, `sdk.py`).
- HTTP routers: `services/api-gateway/app/routers/{integrations,integrations_mcp,notifications,catalog}.py`.
- Data: `IntegrationConnection` (migration 0005), `MCPConnection` (migration 0006);
  approvals/jobs/events/audit are reused, not duplicated.
- Tests: `tests/test_integrations_gateway.py`, `test_integration_slack.py`,
  `test_integration_mcp.py`, `test_integration_phase4.py`, `test_integration_phase5.py`.
