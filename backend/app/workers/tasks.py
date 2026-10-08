"""ARQ jobs with PostgreSQL ownership locks and recovery dispatch."""

from typing import Any
from uuid import UUID

from sqlalchemy import select, text

from app.db.run_repository import RunRepository
from app.db.session import async_session_factory, engine
from app.models.run import Run
from app.orchestrator.executor import DAGExecutor
from app.orchestrator.planner import PlannerExecutor


async def execute_run(ctx: dict[str, Any], run_id: str) -> None:
    del ctx
    await run_job(run_id, planning=False)


async def plan_run(ctx: dict[str, Any], run_id: str) -> None:
    del ctx
    await run_job(run_id, planning=True)


async def run_job(run_id: str, *, planning: bool) -> None:
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
                    if planning:
                        await PlannerExecutor(repository).execute(run)
                    else:
                        await DAGExecutor(repository).execute(run)
        finally:
            await ownership.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_id})


async def recover_runs(ctx: dict[str, Any]) -> None:
    """Repair a crash between confirmation commit and Redis enqueue."""
    async with async_session_factory() as session:
        runs = await session.execute(
            select(Run.id, Run.status).where(Run.status.in_(["PLANNING", "IN_PROGRESS"]))
        )
        for run_id, status in runs:
            job = "plan_run" if status == "PLANNING" else "execute_run"
            prefix = "plan" if status == "PLANNING" else "run"
            await ctx["redis"].enqueue_job(job, str(run_id), _job_id=f"{prefix}:{run_id}")
