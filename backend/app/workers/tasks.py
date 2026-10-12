"""ARQ jobs with PostgreSQL ownership locks and recovery dispatch."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.cleanup_repository import CleanupRepository
from app.db.run_repository import RunRepository
from app.db.session import async_session_factory, engine
from app.models.run import Run
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import PlannerExecutor
from app.services.cleanup import CleanupService
from app.tools.containers import cleanup_containers
from app.workers.ownership import run_lock_key

logger = structlog.get_logger()


async def execute_run(ctx: dict[str, Any], run_id: str) -> None:
    del ctx
    await run_job(run_id, planning=False)


async def plan_run(ctx: dict[str, Any], run_id: str) -> None:
    del ctx
    await run_job(run_id, planning=True)


async def run_job(run_id: str, *, planning: bool) -> None:
    parsed_id = UUID(run_id)
    # A dedicated connection retains a session advisory lock across checkpoint commits.
    lock_id = run_lock_key(parsed_id)
    async with engine.connect() as ownership:
        acquired = await ownership.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_id}
        )
        if not acquired:
            return
        try:
            async with async_session_factory() as session:
                repository = RunRepository(session)
                run = await repository.get(parsed_id)
                if run is not None:
                    if planning:
                        await PlannerExecutor(repository).execute(run)
                    else:
                        await DAGExecutor(repository).execute(run)
        finally:
            try:
                await ownership.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})
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
            query = select(Run.id, Run.status).where(Run.status.in_(["PLANNING", "IN_PROGRESS"]))
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
