"""ARQ jobs with PostgreSQL ownership locks and recovery dispatch."""

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.cleanup_repository import CleanupRepository
from app.db.run_repository import RunRepository
from app.db.session import async_session_factory, engine
from app.models.run import Run
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import PlannerExecutor
from app.services.cleanup import CleanupService
from app.tools.containers import cleanup_containers
from app.workers.logging import log_run_event
from app.workers.ownership import OwnershipLost, run_lock_key

logger = structlog.get_logger()


class DriverConnection(Protocol):
    def is_closed(self) -> bool: ...


async def execute_run(ctx: dict[str, Any], run_id: str) -> None:
    with structlog.contextvars.bound_contextvars(job_id=ctx.get("job_id")):
        await run_job(run_id, planning=False)


async def plan_run(ctx: dict[str, Any], run_id: str) -> None:
    with structlog.contextvars.bound_contextvars(job_id=ctx.get("job_id")):
        await run_job(run_id, planning=True)


async def run_job(run_id: str, *, planning: bool) -> None:
    started = perf_counter()
    with structlog.contextvars.bound_contextvars(
        run_id=run_id, phase="planning" if planning else "execution"
    ):
        logger.info("run_job_started")
        try:
            await _run_job(run_id, planning=planning)
        except asyncio.CancelledError:
            logger.warning("run_job_cancelled")
            raise
        except Exception as exception:
            logger.error("run_job_failed", error_type=type(exception).__name__)
            raise
        else:
            logger.info("run_job_finished", duration_ms=round((perf_counter() - started) * 1000))


async def _run_job(run_id: str, *, planning: bool) -> None:
    parsed_id = UUID(run_id)
    # Bind persistence to the lock's connection: a disconnected owner cannot write
    # through another pooled connection after recovery has acquired the lock.
    lock_id = run_lock_key(parsed_id)
    async with engine.connect() as ownership:
        try:
            acquired = await ownership.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}
            )
        except BaseException:
            # Acquisition may have reached PostgreSQL before cancellation was seen.
            await ownership.invalidate()
            raise
        if not acquired:
            logger.info("run_job_skipped", reason="owned_by_another_worker")
            await ownership.rollback()
            return
        driver: DriverConnection | None = None

        def check_ownership() -> None:
            if driver is None or ownership.closed or ownership.invalidated or driver.is_closed():
                raise OwnershipLost("Execution ownership connection was lost")

        async def watch_ownership() -> None:
            while True:
                check_ownership()
                await asyncio.sleep(get_settings().run_poll_interval)

        execution: asyncio.Task[None] | None = None
        watcher: asyncio.Task[None] | None = None
        try:
            await ownership.commit()
            raw = await ownership.get_raw_connection()
            driver = cast(DriverConnection, raw.driver_connection)
            async with AsyncSession(bind=ownership, expire_on_commit=False) as session:
                repository = RunRepository(session, check_ownership, event_observer=log_run_event)
                run = await repository.get(parsed_id)
                if run is None:
                    logger.warning("run_job_skipped", reason="run_not_found")
                if run is not None:
                    executor = PlannerExecutor(repository) if planning else DAGExecutor(repository)
                    execution = asyncio.create_task(executor.execute(run))
                    watcher = asyncio.create_task(watch_ownership())
                    try:
                        done, _ = await asyncio.wait(
                            {execution, watcher}, return_when=asyncio.FIRST_COMPLETED
                        )
                        if watcher in done:
                            await watcher
                        await execution
                        logger.info(
                            "run_job_result",
                            status=run.status,
                            total_tokens=run.total_tokens,
                            total_time_ms=run.total_time_ms,
                        )
                    finally:
                        execution.cancel()
                        watcher.cancel()
                        await asyncio.gather(execution, watcher, return_exceptions=True)
        finally:
            if driver is None or ownership.invalidated or driver.is_closed():
                await ownership.invalidate()
            else:
                try:
                    await ownership.rollback()
                    await ownership.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id}
                    )
                    await ownership.commit()
                except BaseException:
                    # Never return a connection retaining a session lock to the pool.
                    await ownership.invalidate()
                    raise


async def recover_runs(ctx: dict[str, Any]) -> None:
    """Redis delivery is disposable; PostgreSQL checkpoints are authoritative."""
    settings = get_settings()
    after: UUID | None = None
    # Keyset batches avoid holding a DB transaction open across Redis I/O.
    while True:
        async with async_session_factory() as session:
            query = select(Run.id, Run.status).where(
                Run.status.in_(["PLANNING", "IN_PROGRESS", "PAUSED"])
            )
            if after is not None:
                query = query.where(Run.id > after)
            runs = list(
                (
                    await session.execute(
                        query.order_by(Run.id).limit(settings.recovery_batch_size)
                    )
                ).all()
            )
        if not runs:
            return
        for run_id, status in runs:
            async with engine.connect() as ownership:
                key = run_lock_key(run_id)
                acquired = await ownership.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
                )
                if not acquired:
                    continue
                try:
                    # A fresh ID bypasses stale ARQ retry/result/in-progress keys after a crash.
                    # PostgreSQL ownership/state guards make duplicate deliveries harmless.
                    job = "plan_run" if status == "PLANNING" else "execute_run"
                    await ctx["redis"].enqueue_job(
                        job, str(run_id), _job_id=f"recover:{run_id}:{uuid4().hex}"
                    )
                    logger.info("run_recovery_enqueued", run_id=str(run_id), job=job)
                except Exception as exception:
                    logger.warning(
                        "run_recovery_deferred",
                        run_id=str(run_id),
                        error_type=type(exception).__name__,
                    )
                finally:
                    try:
                        await ownership.execute(
                            text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                        )
                    except BaseException:
                        await ownership.invalidate()
                        raise
        after = runs[-1][0]
        if len(runs) < settings.recovery_batch_size:
            return


async def cleanup_resources(ctx: dict[str, Any]) -> None:
    del ctx
    now = datetime.now(UTC)
    counts = {"files": 0, "events": 0}
    try:
        async with async_session_factory() as session:
            counts = await CleanupService(CleanupRepository(session)).execute(now)
    except Exception as exception:
        # Database outages must not prevent removal of expired code containers.
        logger.warning("retention_cleanup_deferred", error_type=type(exception).__name__)
    containers = await cleanup_containers(now)
    if any(counts.values()) or containers:
        logger.info("resources_cleaned", **counts, containers=containers)
