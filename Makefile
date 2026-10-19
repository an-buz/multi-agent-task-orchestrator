.PHONY: up backend-dev worker frontend-dev migrate migration lint test test-e2e test-e2e-live demo demo-prepare demo-stop

BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000

up:
	docker compose up -d postgres redis

backend-dev:
	cd backend && uv run uvicorn app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

worker:
	cd backend && uv run python -m app.workers.runner

frontend-dev:
	cd frontend && pnpm dev

migrate:
	cd backend && uv run alembic upgrade head

migration:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

lint:
	cd backend && uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy --strict app
	cd frontend && pnpm lint && pnpm typecheck

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

test-e2e:
	cd frontend && pnpm test:e2e

test-e2e-live:
	cd backend && uv run python tests/run_live_e2e.py

frontend-install:
	cd frontend && pnpm install

demo:
	cd backend && uv run python -m app.demo.launcher

demo-prepare:
	cd backend && uv run python -m app.demo.launcher --prepare-only

demo-stop:
	docker compose -p orchestrator-demo -f docker-compose.demo.yml stop
