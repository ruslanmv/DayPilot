SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

UV ?= uv
# Use corepack's pnpm shim so a global pnpm install is not required and no
# `corepack enable` symlink step (which needs root / fails with EACCES on WSL)
# is involved. Override with `make PNPM=pnpm ...` if you have pnpm on PATH.
PNPM ?= pnpm

# Ports. PORT is the single knob; API/WEB derive from it but can be set alone.
PORT ?= 8080
API_HOST ?= 0.0.0.0
API_PORT ?= $(PORT)
WEB_HOST ?= 0.0.0.0
WEB_PORT ?= 5173

# Every service package is importable without a prior editable install, so the
# gateway can pull in the orchestrator/knowledge/model packages directly.
SERVICE_PYTHONPATH := services/api-gateway:services/orchestrator:services/knowledge-service:services/model-serving:services/observability:services/voice-gateway:services/mcp-host

.PHONY: help install install-python install-python-all install-js run run-api run-web serve run-mobile test lint format typecheck build init-db migrate seed seed-reset sim ui-smoke compose compose-runtime clean preview-persona install-persona

define HELP_TEXT

DayPilot Enterprise commands

  Setup
    install              Install Python + JavaScript dependencies
    install-python       Sync the UV-managed Python environment (dev tools)
    install-python-all   Sync Python with all optional extras (RAG, models, obs)
    install-js           Install workspace JavaScript dependencies with pnpm

  Run
    run                  Run the full app locally (API gateway + web UI)
    run-api              Run the FastAPI API gateway (hot reload, auto free port)
    serve                Serve the frontend / dev web UI
    run-web              Alias for `serve` (backwards compatible)
    run-mobile           Run the mobile PWA dev server

  Data
    init-db              Initialize the local database
    migrate              Apply Alembic migrations
    seed                 Seed a realistic-volume workspace (5k tasks)
    seed-reset           Reset seeded rows and reseed the default workspace

  Quality
    test                 Run Python + package-level JavaScript tests
    lint                 Run Python + JavaScript linters
    format               Format Python code with Ruff
    typecheck            Run TypeScript typechecks
    build                Build all JavaScript workspace packages/apps
    ui-smoke             Build operator-web + run the Playwright UI smoke test

  Ops
    sim                  Run the end-to-end 5-day week simulation
    compose              Start the Docker Compose development stack
    compose-runtime      Start runtime + observability Compose profiles
    clean                Remove local caches and virtual environments

Examples:
  make install
  make run                  # backend + frontend together
  make serve                # frontend only
  make run PORT=9000        # start the API on a different port
  make test

endef
export HELP_TEXT

help: ## Show available make targets.
	@printf '%s\n' "$$HELP_TEXT"

install: install-python install-js ## Install Python and JavaScript dependencies for local development.

install-python: ## Create/sync the UV-managed Python environment with dev tools.
	$(UV) sync --group dev

install-python-all: ## Sync Python with all optional extras for RAG, models, and observability.
	$(UV) sync --all-extras --group dev

install-js: ## Install workspace JavaScript dependencies with pnpm.
	$(PNPM) install

run: ## Run the full app locally: API gateway + web UI (Ctrl+C stops both).
	@port=$$($(UV) run python scripts/find_free_port.py $(API_PORT) $(API_HOST)); \
	if [ "$$port" != "$(API_PORT)" ]; then \
	  echo "Port $(API_PORT) is busy; using free port $$port for the API gateway."; \
	fi; \
	echo ""; \
	echo "  Starting DayPilot — API gateway + web UI"; \
	echo "  Web UI:      http://localhost:$(WEB_PORT)"; \
	echo "  API gateway: http://localhost:$$port"; \
	echo "  Web proxy /api → http://localhost:$$port"; \
	echo "  Press Ctrl+C to stop both."; \
	echo ""; \
	trap 'kill 0' INT TERM EXIT; \
	PYTHONPATH="$(SERVICE_PYTHONPATH):$$PYTHONPATH" \
	  $(UV) run uvicorn app.main:app --app-dir services/api-gateway \
	  --host $(API_HOST) --port $$port --reload & \
	DAYPILOT_API_TARGET="http://localhost:$$port" \
	  $(PNPM) --filter @daypilot/operator-web dev -- --host $(WEB_HOST) --port $(WEB_PORT) & \
	wait

run-api: ## Run the FastAPI API gateway with hot reload on an available port.
	@port=$$($(UV) run python scripts/find_free_port.py $(API_PORT) $(API_HOST)); \
	if [ "$$port" != "$(API_PORT)" ]; then \
	  echo "Port $(API_PORT) is busy; using free port $$port for the API gateway."; \
	fi; \
	echo "API gateway: http://localhost:$$port"; \
	PYTHONPATH="$(SERVICE_PYTHONPATH):$$PYTHONPATH" \
	  $(UV) run uvicorn app.main:app --app-dir services/api-gateway \
	  --host $(API_HOST) --port $$port --reload

serve: ## Serve the frontend / dev web UI.
	$(PNPM) --filter @daypilot/operator-web dev -- --host $(WEB_HOST) --port $(WEB_PORT)

run-web: serve ## Alias for `serve` (backwards compatible).

run-mobile: ## Run the mobile PWA app.
	$(PNPM) --filter @daypilot/mobile-pwa dev -- --host 0.0.0.0

test: ## Run Python tests and package-level JavaScript tests.
	$(UV) run pytest -q
	$(PNPM) -r test

lint: ## Run Python and package-level JavaScript linters.
	$(UV) run ruff check services scripts tests
	$(PNPM) -r lint

format: ## Format Python code with Ruff.
	$(UV) run ruff format services scripts tests

typecheck: ## Run TypeScript typechecks across workspace packages.
	$(PNPM) -r typecheck

build: ## Build all JavaScript workspace packages/apps.
	$(PNPM) -r build

init-db: ## Initialize the local database.
	$(UV) run python scripts/init_db.py

migrate: ## Apply Alembic migrations.
	$(UV) run alembic upgrade head

seed: ## Seed a realistic-volume workspace (5k tasks) for dev and load testing.
	$(UV) run python scripts/seed_dev_data.py

seed-reset: ## Reset seeded rows and reseed the default workspace.
	$(UV) run python scripts/seed_dev_data.py --reset

sim: ## Run the end-to-end 5-day week simulation (real pairing + inference).
	$(UV) run python scripts/e2e_week_simulation.py

ui-smoke: ## Build operator-web and run the Playwright UI smoke test.
	$(PNPM) --filter @daypilot/operator-web build
	@echo "Serve dist and run: node tests/ui/smoke.mjs http://localhost:8890"
	@echo "(requires playwright-core + a Chromium binary; set CHROMIUM_PATH if needed)"

compose: ## Start the Docker Compose development stack.
	docker compose up --build

compose-runtime: ## Start runtime and observability Docker Compose profiles.
	docker compose --profile runtime --profile observability up --build

preview-persona: ## Preview the sample HomePilot persona import.
	$(UV) run python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --preview

install-persona: ## Install the sample HomePilot persona import.
	$(UV) run python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --install

clean: ## Remove local caches and virtual environments generated by development commands.
	rm -rf .venv .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
