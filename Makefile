.PHONY: install api web mobile test lint docker preview-persona install-persona tree

install:
	python -m venv .venv || true
	. .venv/bin/activate && pip install -e .[dev]
	pnpm install

api:
	. .venv/bin/activate && uvicorn services.api_gateway.app.main:app --host 0.0.0.0 --port 8080 --reload

web:
	pnpm --filter @daypilot/operator-web dev

mobile:
	pnpm --filter @daypilot/mobile-pwa dev

test:
	. .venv/bin/activate && pytest -q

lint:
	. .venv/bin/activate && ruff check services scripts tests
	docker compose config >/dev/null

docker:
	docker compose up --build

preview-persona:
	python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --preview

install-persona:
	python scripts/import_homepilot_persona.py examples/homepilot-personas/atlas.hpersona --install

tree:
	find . -maxdepth 4 -type f | sort


init-db:
	python scripts/init_db.py

migrate:
	alembic upgrade head

compose:
	docker compose up --build

compose-runtime:
	docker compose --profile runtime --profile observability up --build
