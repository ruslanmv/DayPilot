# DayPilot Operations Runbook

Operational procedures for running DayPilot in production. Pair with
[`docs/deployment.md`](deployment.md) and [`docs/security.md`](security.md).

## Observability

- **Metrics:** every service exposes `/metrics` (Prometheus). Scrape config in
  `infra/monitoring/prometheus.yml`; alert rules in
  `infra/monitoring/alerts.yml`; Grafana dashboard in
  `infra/monitoring/dashboards/daypilot.json`.
- **Request tracing:** the gateway attaches an `X-Request-ID` to every response
  and emits one structured JSON log line per request (method, path, status,
  duration, request + workspace IDs). Clients may pass `X-Request-ID` to
  correlate. Secrets are redacted from all logs.
- **Traces service:** `services/observability` buffers trace events
  (`POST /v1/traces`, `GET /v1/traces`) — the hook point for an OpenTelemetry
  exporter in production.

### Key SLO alerts

| Alert | Meaning | First action |
|---|---|---|
| GatewayHighErrorRate | 5xx rate > 5% for 10m | Check gateway logs by request ID; roll back last deploy if correlated. |
| GatewayHighLatencyP95 | p95 > 1.5s | Check DB and Ollabridge latency panels; scale workers. |
| ModelProviderDegraded | no generations 15m | `GET /v1/providers/health`; confirm Ollabridge reachable; app auto-degrades to mock. |
| AgentRunFailuresHigh | elevated FAILED transitions | Inspect dead-letter jobs (`GET /v1/jobs?state=dead_letter`). |

## RAG quality gate

`daypilot_knowledge.rag_eval.evaluate` scores context precision/recall,
citation coverage, and faithfulness against a labeled set. Run as a scheduled
scorecard; treat a `passed: false` as a release blocker.

## Runbooks

### Ollabridge is down
1. `GET /v1/providers/health` → confirm `status: offline`.
2. The app auto-degrades to the mock backend (visible "degraded" state); no
   outage, reduced quality.
3. Restart/repair the Ollabridge node; health recovers automatically.

### Job backlog / stuck runs
1. `GET /v1/jobs?state=queued` and `?state=dead_letter`.
2. Dead-letter jobs carry `lastError`. Fix the cause, then re-enqueue.
3. Scale workers (they call `worker.process_once/drain`).

### Approvals piling up
1. `GET /v1/approvals/summary` for pending counts by risk.
2. Decide via `POST /v1/approvals/{id}/decide` (RBAC-gated). No write executes
   without an approved approval.

### Backup & restore
- **Database:** run Alembic to the target revision (`alembic upgrade head`);
  restore Postgres from your backup. Migrations 0001–0004 are the schema of
  record.
- **Vector index / generated outputs:** restore `local_data/` volumes; generated
  documents are new versions (originals preserved), so restores are non-lossy.

### Key rotation
- Secrets are read from the environment / managed backend (never the DB). Rotate
  the value, redeploy; `redact()` keeps rotated values out of logs.

### Data deletion / workspace reset
- Retention sweeps (`POST /v1/jobs/retention/sweep`, operator-gated) bound
  events/jobs/audit by age. Full workspace reset deletes workspace-scoped rows;
  audit export first (`GET /v1/approvals/audit/export`).

## Release

- **CI gates:** Python tests + ruff, TS build/typecheck/lint, `docker compose
  config`, Alembic migration validity, and gitleaks secret scan must be green.
- **Web/PWA:** built by `.github/workflows/deploy-web.yml`; deploy `dist/` to
  `daypilot.ruslanmv.com`.
- **Desktop:** `.github/workflows/release-desktop.yml` (Tauri).
- **Rollback:** redeploy the previous build tag; DB migrations are additive —
  avoid destructive down-migrations in production; prefer forward fixes.
