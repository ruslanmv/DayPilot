# Deployment

Canonical domain: `daypilot.ruslanmv.com`.

Deployment modes:

1. **Local desktop** — Tauri shell + local FastAPI runtime.
2. **Local web** — PWA served by Vite or static hosting.
3. **Cloud gateway** — auth, config, optional sync, telemetry metadata.
4. **Hybrid** — cloud-governed and local-first data execution.

The initial Docker Compose stack only starts placeholders for API, Redis, and Postgres.
