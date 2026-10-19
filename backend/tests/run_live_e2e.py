"""Run browsers against disposable PostgreSQL/Redis and real API/worker processes."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

import httpx
import structlog
from app.demo.launcher import stop_process
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
logger = structlog.get_logger(__name__)


def live_environment(
    database_url: str, redis_url: str, api_port: int, web_port: int
) -> dict[str, str]:
    """Override dotenv and inherited credentials in every child process."""
    return {
        **os.environ,
        "APP_ENV": "test",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "DEMO_MODE": "false",
        "E2E_LIVE": "true",
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "LLM_PROVIDER_MODE": "mock",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "TAVILY_API_KEY": "",
        "CODE_EXECUTOR_BACKEND": "disabled",
        "CODE_EXECUTOR_SCOPE": "e2e-live",
        "MOCK_STREAM_DELAY": "0.05",
        "MOCK_STREAM_CHUNK_CHARS": "12",
        "RUN_TOKEN_BUDGET": "100000",
        "CORS_ORIGINS": json.dumps([f"http://localhost:{web_port}"]),
        "NEXT_PUBLIC_API_URL": f"http://localhost:{api_port}/api/v1",
        "E2E_LIVE_API_URL": f"http://localhost:{api_port}/api/v1",
        "E2E_LIVE_BASE_URL": f"http://localhost:{web_port}",
    }


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def guard_providers() -> None:
    """Reject paid SDK clients before any provider request can leave a service."""
    import app.llm.providers as providers

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Real LLM clients are forbidden in live E2E")

    providers.AsyncAnthropic = forbidden
    providers.AsyncOpenAI = forbidden


async def run() -> int:
    node = shutil.which("node")
    playwright = ROOT / "frontend/node_modules/@playwright/test/cli.js"
    if node is None or not playwright.exists():
        raise RuntimeError("Install Node.js and run make frontend-install first")
    postgres = PostgresContainer("postgres:16-alpine")
    redis = RedisContainer("redis:7-alpine")
    processes: list[asyncio.subprocess.Process] = []
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    try:
        await asyncio.to_thread(postgres.start)
        await asyncio.to_thread(redis.start)
        env = live_environment(
            postgres.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg"),
            f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            api_port,
            web_port,
        )
        migration = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "upgrade", "head", cwd=ROOT / "backend", env=env
        )
        if await migration.wait() != 0:
            raise RuntimeError("Live E2E migrations failed")
        with tempfile.TemporaryDirectory(prefix="orchestrator-live-e2e-") as folder:
            with (
                (Path(folder) / "api.log").open(
                    "w+", encoding="utf-8", errors="replace"
                ) as api_log,
                (Path(folder) / "worker.log").open(
                    "w+", encoding="utf-8", errors="replace"
                ) as worker_log,
            ):
                exit_code = 1
                try:
                    for service, log in (("api", api_log), ("worker", worker_log)):
                        processes.append(
                            await asyncio.create_subprocess_exec(
                                sys.executable,
                                str(SCRIPT),
                                "--service",
                                service,
                                "--port",
                                str(api_port),
                                cwd=ROOT / "backend",
                                env=env,
                                stdout=log,
                                stderr=log,
                            )
                        )
                    async with httpx.AsyncClient() as client:
                        for _ in range(120):
                            if any(process.returncode is not None for process in processes):
                                raise RuntimeError("Live E2E service exited during startup")
                            try:
                                response = await client.get(f"http://localhost:{api_port}/health")
                                if response.is_success:
                                    break
                            except httpx.HTTPError:
                                pass
                            await asyncio.sleep(0.5)
                        else:
                            raise RuntimeError("Live E2E API did not become ready")
                    browser = await asyncio.create_subprocess_exec(
                        node,
                        str(playwright),
                        "test",
                        "--config=playwright.live.config.ts",
                        cwd=ROOT / "frontend",
                        env=env,
                    )
                    processes.append(browser)
                    exit_code = await browser.wait()
                    return exit_code
                finally:
                    for process in reversed(processes):
                        await stop_process(process)
                    if exit_code:
                        for name, log in (("api", api_log), ("worker", worker_log)):
                            log.seek(0)
                            logger.info(
                                "live_e2e_service_log", service=name, output=log.read()[-12000:]
                            )
    finally:
        try:
            await asyncio.to_thread(redis.stop)
        finally:
            await asyncio.to_thread(postgres.stop)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=["api", "worker"])
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.service:
        guard_providers()
        if args.service == "api":
            import uvicorn

            uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)
        else:
            from app.workers.runner import run as run_worker

            run_worker()
    else:
        sys.exit(asyncio.run(run()))
