# Deployment

Canonical domain: `daypilot.ruslanmv.com`.

Deployment modes:

1. **Local desktop** — Tauri shell + local FastAPI runtime.
2. **Local web** — PWA served by Vite or static hosting.
3. **Cloud gateway** — auth, config, optional sync, telemetry metadata.
4. **Hybrid** — cloud-governed and local-first data execution.

The initial Docker Compose stack only starts placeholders for API, Redis, and Postgres.

## Echo Show display (`/echo`)

The web build includes a second page, `dist/echo/index.html`, for Amazon Echo Show 21 displays
(built by `vite.echo.config.ts` in the same `pnpm --filter @daypilot/operator-web build`).

- **Single-origin gateway:** served at `/echo` and `/echo/` automatically when the build contains
  it; nothing to configure. Run behind TLS with `DAYPILOT_COOKIE_SECURE=true` and, behind a proxy,
  `uvicorn --proxy-headers --forwarded-allow-ips=<proxy>`.
- **Static hosting:** publish `dist/` as before; `/echo/` resolves to `dist/echo/index.html`
  (`/echo` redirects to it on most hosts). Proxy `/api` on the same host — the Echo needs
  first-party cookies.
- Serve `echo/index.html` with `Cache-Control: no-cache` (the gateway does) so a reloaded display
  picks up a new release; `assets/` are content-hashed.

Details, limitations and the on-device checklist: [echo-show/README.md](echo-show/README.md).
