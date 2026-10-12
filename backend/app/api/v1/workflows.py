"""HTTP adapters for workflow CRUD and graph validation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.workflow_repository import WorkflowRepository
from app.schemas.workflow import WorkflowRead, WorkflowWrite
from app.services.workflows import WorkflowService

router = APIRouter()


def get_workflow_service(session: Annotated[AsyncSession, Depends(get_session)]) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session))


Service = Annotated[WorkflowService, Depends(get_workflow_service)]


@router.get("")
async def list_workflows(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    return await service.list(limit, offset)


@router.post("/validate")
async def validate_workflow(payload: WorkflowWrite, service: Service) -> dict[str, object]:
    await service.validate(payload)
    return {"valid": True, "execution_type": payload.execution_type}


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(payload: WorkflowWrite, service: Service) -> WorkflowRead:
    return await service.create(payload)


@router.get("/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(workflow_id: UUID, service: Service) -> WorkflowRead:
    return await service.read(workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowRead)
async def update_workflow(
    workflow_id: UUID, payload: WorkflowWrite, service: Service
) -> WorkflowRead:
    return await service.update(workflow_id, payload)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: UUID, service: Service) -> None:
    await service.delete(workflow_id)
