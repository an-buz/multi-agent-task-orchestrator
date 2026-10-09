"""Workflow CRUD and graph validation routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowRead, WorkflowWrite, validate_workflow_graph
from app.services.workflows import WorkflowService

router = APIRouter()


async def validate_payload(payload: WorkflowWrite, session: AsyncSession) -> None:
    errors = validate_workflow_graph(payload)
    agent_ids = {step.agent_id for step in payload.steps}
    existing = set(await session.scalars(select(Agent.id).where(Agent.id.in_(agent_ids))))
    missing = agent_ids - existing
    if missing:
        errors.append(f"unknown agent IDs: {', '.join(sorted(map(str, missing)))}")
    if errors:
        raise HTTPException(status_code=422, detail={"code": "invalid_workflow", "errors": errors})


@router.get("")
async def list_workflows(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    total = await session.scalar(select(func.count()).select_from(Workflow))
    workflows = await session.scalars(
        select(Workflow).order_by(Workflow.updated_at.desc()).limit(limit).offset(offset)
    )
    return {
        "items": [WorkflowRead.model_validate(item).model_dump(mode="json") for item in workflows],
        "total": total or 0,
    }


@router.post("/validate")
async def validate_workflow(
    payload: WorkflowWrite, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict[str, object]:
    await validate_payload(payload, session)
    return {"valid": True, "execution_type": payload.execution_type}


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowWrite, session: Annotated[AsyncSession, Depends(get_session)]
) -> Workflow:
    await validate_payload(payload, session)
    workflow = Workflow(
        title=payload.title,
        execution_type=payload.execution_type,
        steps=[step.model_dump(mode="json") for step in payload.steps],
        graph_layout=payload.graph_layout,
    )
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(
    workflow_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Workflow:
    workflow = await session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowRead)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowWrite,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Workflow:
    workflow = await session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await validate_payload(payload, session)
    workflow.title = payload.title
    workflow.execution_type = payload.execution_type
    workflow.steps = [step.model_dump(mode="json") for step in payload.steps]
    workflow.graph_layout = payload.graph_layout
    await session.commit()
    await session.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    await WorkflowService(WorkflowRepository(session)).delete(workflow_id)
