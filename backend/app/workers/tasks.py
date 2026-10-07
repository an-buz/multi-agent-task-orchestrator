"""ARQ jobs with PostgreSQL ownership locks and recovery dispatch."""

from typing import Any
from uuid import UUID

from sqlalchemy import select, text

from app.db.run_repository import RunRepository
from app.db.session import async_session_factory, engine
from app.models.run import Run
from app.orchestrator.executor import DAGExecutor


async def execute_run(ctx: dict[str, Any], run_id: str) -> None:
    del ctx
    parsed_id = UUID(run_id)
    # A dedicated connection retains a session advisory lock across checkpoint commits.
    lock_id = int.from_bytes(parsed_id.bytes[:8], "big", signed=True)
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
                    await DAGExecutor(repository).execute(run)
        finally:
            await ownership.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})


async def recover_runs(ctx: dict[str, Any]) -> None:
    """Repair a crash between confirmation commit and Redis enqueue."""
    async with async_session_factory() as session:
        run_ids = await session.scalars(select(Run.id).where(Run.status == "IN_PROGRESS"))
        for run_id in run_ids:
            await ctx["redis"].enqueue_job("execute_run", str(run_id), _job_id=f"run:{run_id}")
