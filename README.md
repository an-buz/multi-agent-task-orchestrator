# Multi-Agent Task Orchestrator

A web app for building teams of AI agents, connecting them in visual workflows, and monitoring execution in real time. Review and confirm a task plan before running it, retry failed steps, and export results. Supports Anthropic, OpenAI, Gemini, and local mock responses.

## Run locally

Requires Python 3.14, uv, Node.js with pnpm 11, Make, and Docker Compose with Docker running. Run commands from the repository root.

1. Copy the environment templates (skip files that already exist):

   ```sh
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env.local
   ```

2. Install dependencies, start PostgreSQL and Redis, and apply migrations:

   ```sh
   make frontend-install
   make up
   make migrate
   ```

   Backend dependencies are installed automatically by uv.

3. Run each command in a separate terminal:

   ```sh
   make backend-dev
   ```

   ```sh
   make worker
   ```

   ```sh
   make frontend-dev
   ```

Open [the app](http://localhost:3000) or [API docs](http://localhost:8000/docs). Create agents and a workflow, submit a task, then review and confirm its plan.

The default mode uses mock responses without API keys. For real models, set `LLM_PROVIDER_MODE=real` and the relevant `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY` in `backend/.env`. Restart the API and worker, then select the discovered models for agent defaults and the planner in **Settings**.
