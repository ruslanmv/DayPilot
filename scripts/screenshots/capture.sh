#!/usr/bin/env bash
# Capture the documentation screenshots from the real app.
#
# Everything runs against a throwaway SQLite database and two throwaway ports,
# so a developer's own workspace is never touched and never photographed. The
# seeders drive the real engines — the screenshots show what the product
# produces, not hand-written copy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

WORK="$(mktemp -d -t daypilot-shots-XXXXXX)"
export DATABASE_URL="sqlite:///${WORK}/daypilot.db"
API_PORT="${SHOTS_API_PORT:-8098}"
WEB_PORT="${SHOTS_WEB_PORT:-8099}"
PY="${PYTHON:-.venv/bin/python}"
export PYTHONPATH="services/api-gateway:services/orchestrator:services/knowledge-service:services/model-serving:services/observability"

api_pid=""; web_pid=""
cleanup() {
  [[ -n "$web_pid" ]] && kill "$web_pid" 2>/dev/null || true
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "==> schema + seed data (${WORK})"
"$PY" scripts/init_db.py >/dev/null
# The agents shots are the only ones with an external dependency: portraits come
# from the HomePilot gallery. Capture the seeder's own verdict rather than
# guessing, so a run without network access leaves the checked-in images alone
# instead of quietly replacing portraits with initials circles.
AGENTS_SEED_LOG="${WORK}/agents-seed.log"
if "$PY" scripts/screenshots/seed_agents.py >"$AGENTS_SEED_LOG" 2>&1; then
  grep -q PORTRAITS_UNAVAILABLE "$AGENTS_SEED_LOG" && SHOOT_AGENTS=0 || SHOOT_AGENTS=1
else
  echo "    (agents seed failed — see $AGENTS_SEED_LOG)"
  SHOOT_AGENTS=0
fi
# Standup before the workspace: it compiles its draft from the day's evidence,
# and the curated tour data would otherwise crowd its three bullets.
"$PY" scripts/screenshots/seed_standup.py
"$PY" scripts/screenshots/seed_workspace.py
# Last: a connected Outlook and the day built around a real meeting.
"$PY" scripts/screenshots/seed_calendar.py
# The Slack morning, ingested through the real classify/draft pipeline so the
# badges and counts in the shots are produced rather than written.
"$PY" scripts/screenshots/seed_slack.py

echo "==> api on :${API_PORT}"
# The optional Email module, on its documented mock backend — otherwise the
# Email screenshots show the connect-your-mailbox state rather than the
# workspace. Sending stays approval-gated either way.
export DAYPILOT_EMAIL_ENABLED=true
export DAYPILOT_EMAIL_PROVIDER=mock
# The Slack workspace is optional and off by default; the documentation shots
# need it on, on both sides.
export DAYPILOT_SLACK_WORKSPACE_ENABLED=1
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" >"${WORK}/api.log" 2>&1 &
api_pid=$!
for _ in $(seq 1 40); do
  curl -sf -o /dev/null "http://127.0.0.1:${API_PORT}/health" && break
  sleep 0.5
done

# The shell shows a bootstrap screen until an owner exists; create one so the
# screenshots land on the product rather than on first-run setup.
curl -sf -X POST "http://127.0.0.1:${API_PORT}/v1/auth/bootstrap" \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"daypilot-demo-2026","displayName":"Ruslan M.","workspaceName":"DayPilot"}' \
  >/dev/null 2>&1 || true

echo "==> web on :${WEB_PORT}"
( cd apps/operator-web && \
  DAYPILOT_API_TARGET="http://127.0.0.1:${API_PORT}" \
  VITE_DAYPILOT_API_BASE=/api VITE_DAYPILOT_DEMO_MODE=false \
  VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED=true \
  npx vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort >"${WORK}/web.log" 2>&1 ) &
web_pid=$!
for _ in $(seq 1 60); do
  curl -sf -o /dev/null "http://127.0.0.1:${WEB_PORT}/" && break
  sleep 0.5
done

echo "==> shooting"
export SHOOT_BASE="http://127.0.0.1:${WEB_PORT}"
"$PY" scripts/screenshots/shoot_tour.py
"$PY" scripts/screenshots/shoot_standup.py
"$PY" scripts/screenshots/shoot_slack.py
if [[ "$SHOOT_AGENTS" == "1" ]]; then
  "$PY" scripts/screenshots/shoot.py || echo "    (agents shots skipped)"
else
  echo "==> agents shots SKIPPED — no portraits available on this machine."
  echo "    The checked-in images were captured with gallery access; overwriting"
  echo "    them here would swap the portraits for initials. See docs/agents-ui-screenshots.md"
  echo "    to capture them offline via SEED_PORTRAIT_DIR."
fi

echo "==> done — docs/assets/screenshots/"
