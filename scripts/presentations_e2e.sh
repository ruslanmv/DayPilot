#!/usr/bin/env bash
# Presentations browser end-to-end: builds the web UI, starts a throwaway gateway on a temporary
# SQLite database, runs tests/ui/dmind-e2e.mjs against it, then cleans up.
# Needs playwright-core and a Chromium binary (see the header of the test file).
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-uv}"
PNPM="${PNPM:-pnpm}"
tmp="$(mktemp -d)"
pid=""
cleanup() { [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; rm -rf "$tmp"; }
trap cleanup EXIT

"$PNPM" --filter @daypilot/operator-web build
port="$("$UV" run python scripts/find_free_port.py "${PORT:-8890}" 127.0.0.1)"
export DAYPILOT_PRESENTATIONS=true
# Expert builds run only where the sandbox is available (setpriv/unshare as root); the step skips otherwise.
export DAYPILOT_PRESENTATIONS_EXPERT=true
export DAYPILOT_PRESENTATIONS_DIR="$tmp/store"
export DATABASE_URL="sqlite:///$tmp/dmind-e2e.db"
# Deterministic failure path unless a real Matrix Designer is supplied.
export MATRIX_DESIGNER_URL="${MATRIX_DESIGNER_URL:-http://127.0.0.1:9}"
export PYTHONPATH="services/api-gateway:services/orchestrator:services/knowledge-service:services/model-serving:services/observability:services/voice-gateway:services/mcp-host"
"$UV" run uvicorn app.main:app --app-dir services/api-gateway --host 127.0.0.1 --port "$port" >"$tmp/gateway.log" 2>&1 &
pid=$!
for _ in $(seq 1 60); do
  curl -fs "http://127.0.0.1:$port/v1/diagrams" >/dev/null 2>&1 && break
  sleep 0.5
done
node tests/ui/presentations-e2e.mjs "http://127.0.0.1:$port" || { echo "--- gateway log"; tail -30 "$tmp/gateway.log"; exit 1; }
