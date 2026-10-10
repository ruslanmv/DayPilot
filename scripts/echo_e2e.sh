#!/usr/bin/env bash
# Echo Show display mode (/echo) browser end-to-end: builds the web UI, starts a throwaway
# gateway that requires sign-in on a temporary SQLite database, seeds it through the API,
# runs tests/ui/echo-e2e.mjs against it, then cleans up.
# Needs playwright (or playwright-core) and a Chromium binary (see the header of the test).
# ECHO_SCREENSHOTS=<dir> keeps the screenshots.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-uv}"
PNPM="${PNPM:-pnpm}"
tmp="$(mktemp -d)"
pid=""
cleanup() { [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; rm -rf "$tmp"; }
trap cleanup EXIT

"$PNPM" --filter @daypilot/operator-web build
port="$("$UV" run python scripts/find_free_port.py "${PORT:-8891}" 127.0.0.1)"
export DATABASE_URL="sqlite:///$tmp/echo-e2e.db"
export DAYPILOT_REQUIRE_SESSION=true
export PYTHONPATH="services/api-gateway:services/orchestrator:services/knowledge-service:services/model-serving:services/observability:services/voice-gateway:services/mcp-host"
"$UV" run uvicorn app.main:app --app-dir services/api-gateway --host 127.0.0.1 --port "$port" >"$tmp/gateway.log" 2>&1 &
pid=$!
for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$port/health" >/dev/null 2>&1 && break
  sleep 0.5
done
"$UV" run python tests/ui/echo_seed.py "http://127.0.0.1:$port"
node tests/ui/echo-e2e.mjs "http://127.0.0.1:$port" || { echo "--- gateway log"; tail -30 "$tmp/gateway.log"; exit 1; }
