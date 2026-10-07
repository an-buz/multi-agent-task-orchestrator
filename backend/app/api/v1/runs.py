"""Run creation, plan review, and run state routes."""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.agent import Agent
from app.models.run import Run
from app.models.workflow import Workflow
from app.schemas.run import RunCreate, RunPlan, RunPlanStep, RunPlanUpdate, RunRead

router = APIRouter()


def serialize_run(run: Run, workflow_title: str) -> RunRead:
    """Build the public response with the workflow title included."""
    return RunRead(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_title=workflow_title,
        task=run.task,
        context_text=run.context_text,
        status=run.status,
        plan=RunPlan.model_validate(run.plan),
        final_report=run.final_report,
        total_tokens=run.total_tokens,
        total_time_ms=run.total_time_ms,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


async def build_mock_plan(workflow: Workflow, task: str, session: AsyncSession) -> dict[str, Any]:
    """Create a deterministic plan for the configured mock-data mode."""
    steps = workflow.steps
    agent_ids = {UUID(str(step["agent_id"])) for step in steps}
    agents = await session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))
    agents_by_id = {agent.id: agent for agent in agents}
    missing = agent_ids - agents_by_id.keys()
    if missing:
        raise HTTPException(
            status_code=409,
            detail={"code": "workflow_agents_missing", "agent_ids": sorted(map(str, missing))},
        )

    planned_steps = []
    for step in sorted(steps, key=lambda item: int(item["step_number"])):
        agent_id = UUID(str(step["agent_id"]))
        agent = agents_by_id[agent_id]
        planned_steps.append(
            RunPlanStep(
                step_number=int(step["step_number"]),
                agent_id=agent_id,
                agent_name=agent.name,
                subtask=f"{agent.role}: {task}",
                depends_on=list(step.get("depends_on", [])),
            ).model_dump(mode="json")
        )
    return RunPlan(
        summary=f"Mock plan for workflow: {workflow.title}", steps=planned_steps
    ).model_dump(mode="json")


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunRead:
    """Persist a run with a deterministic plan for mock-data development."""
    workflow = await session.get(Workflow, payload.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    plan = await build_mock_plan(workflow, payload.task, session)
    run = Run(
        workflow_id=workflow.id,
        task=payload.task,
        context_text=payload.context_text,
        status="AWAITING_CONFIRMATION",
        plan=plan,
        total_tokens=0,
        total_time_ms=0,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return serialize_run(run, workflow.title)


@router.get("")
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    """List runs in reverse creation order."""
    total = await session.scalar(select(func.count()).select_from(Run))
    rows = await session.execute(
        select(Run, Workflow.title)
        .join(Workflow, Workflow.id == Run.workflow_id)
        .order_by(Run.created_at.desc(), Run.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [serialize_run(run, title).model_dump(mode="json") for run, title in rows],
        "total": total or 0,
    }


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]) -> RunRead:
    """Return the current run and reviewed plan."""
    result = await session.execute(
        select(Run, Workflow.title)
        .join(Workflow, Workflow.id == Run.workflow_id)
        .where(Run.id == run_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run, title = row
    return serialize_run(run, title)


@router.patch("/{run_id}/plan", response_model=RunRead)
async def update_run_plan(
    run_id: UUID,
    payload: RunPlanUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunRead:
    """Update planned subtasks while preserving the workflow graph."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "AWAITING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="Run plan can no longer be edited")

    current = RunPlan.model_validate(run.plan)
    current_by_number = {step.step_number: step for step in current.steps}
    updates = {step.step_number: step for step in payload.steps}
    if set(updates) != set(current_by_number):
        raise HTTPException(status_code=422, detail="Plan must contain every workflow step")
    for number, updated in updates.items():
        original = current_by_number[number]
        if updated.agent_id != original.agent_id or updated.depends_on != original.depends_on:
            raise HTTPException(status_code=422, detail="Plan edits may only change subtask text")
        original.subtask = updated.subtask
    run.plan = current.model_dump(mode="json")
    await session.commit()
    workflow = await session.get(Workflow, run.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=409, detail="Run workflow no longer exists")
    return serialize_run(run, workflow.title)


@router.post("/{run_id}/confirm", response_model=RunRead)
async def confirm_run(
    run_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> RunRead:
    """Confirm a reviewed plan and transition it to execution state."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "AWAITING_CONFIRMATION":
        raise HTTPException(status_code=409, detail="Run is not awaiting confirmation")
    run.status = "IN_PROGRESS"
    run.started_at = datetime.now(UTC)
    await session.commit()
    workflow = await session.get(Workflow, run.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=409, detail="Run workflow no longer exists")
    return serialize_run(run, workflow.title)
