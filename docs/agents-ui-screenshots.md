# Regenerating the agents-UI screenshots

The images in `docs/assets/screenshots/agents/` are captured from the **running**
app (built + served single-origin by the gateway) against a seeded demo
workspace. Playwright is a transient sandbox dependency — install it only for the
capture, then remove it.

```bash
# From the repo root.
export SCRATCH=$(mktemp -d)
export DATABASE_URL="sqlite:///$SCRATCH/shots.db"
export PYTHONPATH="services/api-gateway:services/orchestrator:services/knowledge-service:services/model-serving:services/observability:services/voice-gateway:services/mcp-host"
export DAYPILOT_HOMEPILOT_RUNTIME_ENABLED=true DAYPILOT_HOMEPILOT_SYNC_ENABLED=true \
       DAYPILOT_HOMEPILOT_CHAT_ENABLED=true DAYPILOT_HOMEPILOT_DELEGATION_ENABLED=true \
       DAYPILOT_AUTO_MIGRATE=0

# 1. Build the web UI (the gateway serves the built SPA single-origin).
pnpm --filter @daypilot/operator-web build

# 2. Fresh DB → migrate → seed demo agents + a Scarlett workspace.
#    The seed pulls each agent's portrait from the HomePilot Community Gallery.
#    For a fully offline run, pre-download the bundles and point the seed at them:
#      mkdir -p /tmp/portraits && for id in scarlett_exec_secretary atlas_research_assistant \
#        felix_project_navigator luca_calendar_strategist priya_inbox_alchemist \
#        elena_knowledge_curator soren_shell_operator diana_office_navigator; do \
#        curl -sSL -o /tmp/portraits/$id.hpersona \
#          https://homepilot-persona-gallery.cloud-data.workers.dev/p/$id/1.0.0; done
#      export SEED_PORTRAIT_DIR=/tmp/portraits
.venv/bin/alembic upgrade head
.venv/bin/python scripts/screenshots/seed_agents.py

# 3. Start the gateway (serves the SPA at /, strips /api for API calls).
.venv/bin/uvicorn app.main:app --app-dir services/api-gateway --host 127.0.0.1 --port 8099 &

# 4. Create the first owner so the shell renders (auth is off, but bootstrap gates it).
curl -s -X POST http://127.0.0.1:8099/v1/auth/bootstrap -H 'Content-Type: application/json' \
  -d '{"email":"jane@acme.com","password":"daypilot-demo-123","displayName":"Ruslan M.","workspaceName":"Acme Corporation"}'

# 5. Capture (Playwright + the pre-installed Chromium). shoot.py pre-marks
#    first-run setup complete so the onboarding wizard never overlays.
uv pip install playwright
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers SHOOT_OUT=docs/assets/screenshots/agents \
  .venv/bin/python scripts/screenshots/shoot.py

# 6. Clean up.
pkill -f "uvicorn app.main" || true
uv pip uninstall playwright || true
```

Routes captured (hash-routed SPA): `#/agents`, `#/agents/scarlett`,
`#/agents/add`, plus a narrow-viewport workspace shot. Adjust `scripts/
screenshots/seed_agents.py` to change the demo staff.
