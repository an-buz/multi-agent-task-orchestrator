.PHONY: up backend-dev worker frontend-dev migrate migration lint test test-e2e

up:
	docker compose up -d postgres redis

backend-dev:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd backend && uv run arq app.workers.settings.WorkerSettings

frontend-dev:
	cd frontend && pnpm dev

migrate:
	cd backend && uv run alembic upgrade head

migration:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

lint:
	cd backend && uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy --strict app
	cd frontend && pnpm exec eslint . && pnpm exec tsc --noEmit

test:
	cd backend && uv run pytest

test-e2e:
	cd frontend && pnpm exec playwright test
