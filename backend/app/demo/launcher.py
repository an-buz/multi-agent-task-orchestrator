"""Start an isolated demo stack with one command and stop its child processes together."""

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.demo.catalogue import DEMO_TASK, seed_demo

ROOT = Path(__file__).resolve().parents[3]
logger = structlog.get_logger(__name__)


class DemoPorts(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEMO_")

    backend_port: int = Field(default=18000, ge=1, le=65535)
    frontend_port: int = Field(default=3000, ge=1, le=65535)
    database_port: int = Field(default=15432, ge=1, le=65535)
    redis_port: int = Field(default=17379, ge=1, le=65535)


def demo_environment(ports: DemoPorts) -> dict[str, str]:
    """Override local .env files for every demo process, including migrations."""
    return {
        **os.environ,
        "DEMO_MODE": "true",
        "DEMO_DATABASE_PORT": str(ports.database_port),
        "DEMO_REDIS_PORT": str(ports.redis_port),
        "APP_ENV": "development",
        "DATABASE_URL": (
            f"postgresql+asyncpg://demo:demo@127.0.0.1:{ports.database_port}/orchestrator_demo"
        ),
        "REDIS_URL": f"redis://127.0.0.1:{ports.redis_port}/0",
        "LLM_PROVIDER_MODE": "mock",
        "CODE_EXECUTOR_BACKEND": "disabled",
        "CODE_EXECUTOR_SCOPE": "orchestrator-demo",
        "MOCK_STREAM_CHUNK_CHARS": "32",
        "MOCK_STREAM_DELAY": "0.12",
        "MAX_PARALLEL_STEPS": "4",
        "CORS_ORIGINS": json.dumps([f"http://localhost:{ports.frontend_port}"]),
        "NEXT_PUBLIC_API_URL": f"http://localhost:{ports.backend_port}/api/v1",
    }


async def checked(command: list[str], env: dict[str, str], cwd: Path) -> None:
    process = await asyncio.create_subprocess_exec(*command, cwd=cwd, env=env)
    if await process.wait() != 0:
        raise RuntimeError(f"Demo setup failed: {command[0]}")


async def seed(settings: Settings) -> None:
    engine = create_async_engine(str(settings.database_url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await seed_demo(session, settings)
    finally:
        await engine.dispose()


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        # Next.js creates a child server; terminate only this launcher's process tree.
        cleanup = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await cleanup.wait()
    else:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()


async def main(*, prepare_only: bool = False) -> None:
    ports = DemoPorts()
    env = demo_environment(ports)
    node = shutil.which("node")
    next_cli = ROOT / "frontend/node_modules/next/dist/bin/next"
    if not prepare_only and (node is None or not next_cli.exists()):
        raise RuntimeError("Install Node.js and run make frontend-install before make demo")
    os.environ.update(env)
    get_settings.cache_clear()
    settings = get_settings()
    await checked(
        [
            "docker",
            "compose",
            "-p",
            "orchestrator-demo",
            "-f",
            "docker-compose.demo.yml",
            "up",
            "-d",
            "--wait",
        ],
        env,
        ROOT,
    )
    await checked([sys.executable, "-m", "alembic", "upgrade", "head"], env, ROOT / "backend")
    await seed(settings)
    logger.info("demo_prepared", agents=5, workflows=3, suggested_task=DEMO_TASK)
    if prepare_only:
        return
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports.backend_port),
            ],
            ROOT / "backend",
        ),
        ([sys.executable, "-m", "app.workers.runner"], ROOT / "backend"),
        (
            [
                str(node),
                str(next_cli),
                "dev",
                "--hostname",
                "localhost",
                "--port",
                str(ports.frontend_port),
            ],
            ROOT / "frontend",
        ),
    ]
    processes: list[asyncio.subprocess.Process] = []
    monitors: list[asyncio.Task[int]] = []
    try:
        for command, cwd in commands:
            processes.append(await asyncio.create_subprocess_exec(*command, cwd=cwd, env=env))
        logger.info("demo_starting", url=f"http://localhost:{ports.frontend_port}")
        monitors = [asyncio.create_task(process.wait()) for process in processes]
        await asyncio.wait(monitors, return_when=asyncio.FIRST_COMPLETED)
        raise RuntimeError("A demo process exited; stopping the remaining demo processes")
    finally:
        for process in reversed(processes):
            await stop_process(process)
        for monitor in monitors:
            monitor.cancel()
        await asyncio.gather(*monitors, return_exceptions=True)


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(main(prepare_only=args.prepare_only))
    except KeyboardInterrupt:
        logger.info("demo_stopped", containers="kept for the next demo; use make demo-stop to stop")


if __name__ == "__main__":
    run()
