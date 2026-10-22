# Multi-Agent Task Orchestrator

A web application for configuring AI agents, designing workflows, and monitoring task execution in real time. Build a team of specialized agents, connect their work in a visual graph, and review an execution plan before running it.

The project includes a FastAPI backend, an ARQ worker, and a Next.js dashboard. PostgreSQL stores configuration, run state, results, and durable events; Redis provides the worker queue.

## Features

- **Agent configuration:** define roles, system prompts, models, generation settings, and permitted tools.
- **Visual workflow editor:** create sequential, parallel, and hybrid workflows with dependency graphs, input templates, and graph validation.
- **Plan Preview:** decompose a task into steps and review the plan. Execution starts only after explicit confirmation.
- **Execution monitoring:** follow step statuses, agent output, tool activity, token usage, and elapsed time through Server-Sent Events (SSE).
- **Failure recovery:** retry a failed step while preserving completed work; cancel runs and inspect run history.
- **Context and tools:** attach text, Markdown, or JSON context; use calculator, web search, file reading, and optional Docker-isolated code execution.
- **Reports:** inspect completed results and export them as Markdown, JSON, or PDF.
- **Model settings and themes:** manage model availability and defaults, and switch between light and dark themes.
- **Prepared demo:** explore five agents and three workflows without provider credentials.

## Technology stack

| Layer            | Technologies                                                                      |
| ---------------- | --------------------------------------------------------------------------------- |
| Frontend         | Next.js 16 App Router, React 19, TypeScript, Tailwind CSS, shadcn/ui with Base UI |
| Workflow editor  | React Flow (`@xyflow/react`)                                                      |
| Data and forms   | TanStack Query, React Hook Form, Zod                                              |
| Backend          | Python 3.14, FastAPI, Pydantic v2, async SQLAlchemy, Alembic                      |
| Storage and jobs | PostgreSQL 16, Redis 7, ARQ                                                       |
| LLM integration  | Anthropic, OpenAI, and mock providers behind a shared interface                   |
| Quality checks   | Ruff, mypy strict, ESLint, TypeScript, pytest, Node.js test runner, Playwright    |

## Prerequisites

- Python **3.14** and **uv**. The backend currently requires Python `>=3.14,<3.15`.
- Node.js compatible with Next.js 16 and **pnpm 11**. The frontend pins `pnpm@11.19.0` in `package.json`.
- Docker with Docker Compose and a running Docker engine.

Run the following commands from the repository root unless stated otherwise. Use pnpm for frontend dependencies.

## Quick start: prepared demo

```sh
make frontend-install
make demo
```

The launcher starts isolated PostgreSQL and Redis containers, applies migrations, seeds the demo catalog, and starts the API, worker, and frontend. uv resolves backend dependencies automatically.

Open [the dashboard](http://localhost:3000) after Next.js reports that it is ready.

1. Select a **Demo: Task board release** workflow: sequential, parallel, or hybrid.
2. Enter: `Prepare the task board release with task creation, status filters, and release notes.`
3. Request a plan, review Plan Preview, and confirm execution.
4. Follow the five agents in the monitor, then inspect or export the completed report.

Demo responses and token usage are fixed fictional fixtures for this release scenario. They do not adapt to arbitrary tasks. No API keys are required, and code execution is disabled. Demo storage is separate from the regular development database and queue.

| Demo service | Default address          |
| ------------ | ------------------------ |
| Frontend     | `http://localhost:3000`  |
| API          | `http://localhost:18000` |
| PostgreSQL   | `127.0.0.1:15432`        |
| Redis        | `127.0.0.1:17379`        |

Press **Ctrl+C** to stop the application processes. To stop the demo containers as well:

```sh
make demo-stop
```

Persisted demo data remains available for subsequent launches.

## Local development

### 1. Configure the application

Copy the environment templates without overwriting existing local settings:

```sh
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

The templates default to mock LLM responses and disabled code execution, so you can explore the application without provider credentials.

### 2. Install dependencies and prepare storage

```sh
make frontend-install
make up
make migrate
```

`make up` starts the regular PostgreSQL and Redis containers. `make migrate` resolves backend dependencies through uv and applies Alembic migrations.

### 3. Start the application

Run each command in a separate terminal:

```sh
make backend-dev
```

```sh
make worker
```

```sh
make frontend-dev
```

| Service        | Default address                                       |
| -------------- | ----------------------------------------------------- |
| Frontend       | [localhost:3000](http://localhost:3000)               |
| API            | `http://localhost:8000/api/v1`                        |
| Swagger UI     | [localhost:8000/docs](http://localhost:8000/docs)     |
| ReDoc          | [localhost:8000/redoc](http://localhost:8000/redoc)   |
| Liveness check | [localhost:8000/health](http://localhost:8000/health) |
| PostgreSQL     | `127.0.0.1:5432`                                      |
| Redis          | `127.0.0.1:16379`                                     |

Create agents, add them to a workflow, and submit a task from the dashboard. A fresh regular database has no prepared demo catalog. Keep the worker running for planning and execution.

### Configuration

| Variable                              | Purpose / default                                                                |
| ------------------------------------- | -------------------------------------------------------------------------------- |
| `DATABASE_URL`                        | Async PostgreSQL DSN; `postgresql+asyncpg://app:app@localhost:5432/orchestrator` |
| `REDIS_URL`                           | Worker queue connection; `redis://localhost:16379/0`                             |
| `LLM_PROVIDER_MODE`                   | `mock` by default; set to `real` for provider calls                              |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Server-side credentials for the providers used by your agents and planner        |
| `PLANNER_MODEL`                       | Planner model registry key; defaults to `claude-sonnet`                          |
| `TAVILY_API_KEY`                      | Credentials for the web search tool                                              |
| `CODE_EXECUTOR_BACKEND`               | `disabled` by default; `docker` enables isolated execution                       |
| `MAX_PARALLEL_STEPS`                  | Maximum concurrent workflow steps; defaults to `4`                               |
| `CORS_ORIGINS`                        | JSON array of allowed frontend origins; defaults to `["http://localhost:3000"]`  |
| `NEXT_PUBLIC_API_URL`                 | Frontend setting; defaults to `http://localhost:8000/api/v1`                     |
| `EXPORT_PDF_FONT_PATH`                | Optional override for the TrueType font used in PDF reports                      |

For real provider calls, set `LLM_PROVIDER_MODE=real` and `DEMO_MODE=false`, supply the relevant credentials, and check both agent and planner model settings. For an OpenAI-only deployment, set `PLANNER_MODEL=gpt-4o` and choose OpenAI agents. Restart the API and worker after changing their configuration.

Provider keys stay on the backend. Never put secrets in `NEXT_PUBLIC_*` variables. Code execution requires Docker and runs with network access disabled and resource limits. File Reader also supports PDF attachments. See [backend settings](backend/app/core/config.py) and [the environment template](backend/.env.example) for additional limits and options.

If you change the frontend port, update `CORS_ORIGINS`. If you change the API address, update `NEXT_PUBLIC_API_URL` and restart the frontend. Regular and demo servers need different ports when running simultaneously; demo build artifacts use `.next/demo`.

## Development commands

| Command                          | Description                                                               |
| -------------------------------- | ------------------------------------------------------------------------- |
| `make up`                        | Start regular PostgreSQL and Redis containers                             |
| `make backend-dev`               | Start the API with reload on port 8000                                    |
| `make worker`                    | Start the ARQ worker                                                      |
| `make frontend-dev`              | Start the Next.js development server                                      |
| `make frontend-install`          | Install frontend dependencies with pnpm                                   |
| `make migrate`                   | Apply database migrations                                                 |
| `make migration m="description"` | Create an autogenerated Alembic migration                                 |
| `make lint`                      | Run Ruff checks, formatting checks, mypy, ESLint, and TypeScript checks   |
| `make test`                      | Run backend unit/integration tests and frontend unit tests                |
| `make test-e2e`                  | Run Playwright browser tests                                              |
| `make test-e2e-live`             | Run the full-stack browser lifecycle with disposable storage and mock LLM |
| `make demo`                      | Prepare and launch the complete demo                                      |
| `make demo-prepare`              | Prepare demo containers, migrations, and seed data only                   |
| `make demo-stop`                 | Stop demo containers while keeping their data                             |

## Testing

Run the required checks from the repository root:

```sh
make lint && make test
```

Backend integration tests use temporary PostgreSQL and Redis containers through Testcontainers, so Docker must be running. Tests enforce mock LLM mode and reject live provider clients.

Install Chromium once from `frontend/` before running browser tests:

```sh
pnpm exec playwright install chromium
```

Then run `make test-e2e` from the root. Playwright starts or reuses the frontend on port 3000. The browser suite uses mocked API responses; it does not establish live provider or full backend integration coverage.

For a real frontend/API/worker/storage check, run `make test-e2e-live`. It creates temporary PostgreSQL and Redis containers, applies migrations, and starts isolated API, worker, and frontend processes on available ports. The light/dark scenarios create agents and a sequential workflow through the UI, confirm the plan, verify SSE completion and persisted results, and download the JSON report. LLM responses are deterministic mocks; real provider clients are blocked. The launcher cleans up its processes and containers after the run. See [testing details](docs/testing.md).

## Project structure

```text
backend/
  app/
    api/v1/       REST routes and SSE endpoints
    core/         Configuration, logging, and domain errors
    db/           Database sessions and repositories
    models/       SQLAlchemy models
    schemas/      Pydantic request, response, and event schemas
    services/     Business logic and report export
    orchestrator/ Planning, DAG scheduling, and step execution
    llm/          Providers, model registry, context handling, and retry
    tools/        Tool runtime and Docker isolation
    events/       Durable execution events
    workers/      ARQ jobs and recovery
    demo/         Isolated demo launcher, catalog, and fixtures
  alembic/        Database migrations
  tests/          Unit tests, integration tests, and mock fixtures
frontend/
  src/app/        Routes, layouts, and global styles
  src/features/   Agents, models, workflows, runs, monitoring, files, settings
  src/components/ Shared application and UI components
  src/lib/        HTTP client and shared utilities
  tests/          Frontend unit tests
  e2e/            Playwright browser tests
docs/             Architecture, API, UX, testing, demo, and progress notes
```

Backend dependencies follow `api → services → repositories / orchestrator / llm / tools`. Workflow execution runs in the worker, outside HTTP request handlers. Run checkpoints and events are persisted in PostgreSQL; SSE replays durable events after reconnects.

## Agent findings and user decisions

Agents can finish a review with the built-in `request_user_decision` control tool
when they find problems requiring another agent's work. New steps stop immediately;
active branches finish before the run becomes paused. The dashboard and Run details
show the findings and offer **Assign fixes**, **Continue without fixes**, and
**Cancel run**. Assigning fixes adds a task for the selected available agent and a
verification by the original reviewer, then resumes pending work. Previous results
and usage are preserved. Every new finding requires a fresh explicit decision.
