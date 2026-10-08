"""HTTP adapters for run planning and confirmation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.run_repository import RunRepository
from app.db.session import get_session
from app.schemas.context_file import ContextFileRead
from app.schemas.run import RunCreate, RunPlanUpdate, RunRead
from app.services.export import ExportFormat, export_result
from app.services.runs import RunService
from app.workers.queue import enqueue_plan, enqueue_run

router = APIRouter()


def get_run_service(session: Annotated[AsyncSession, Depends(get_session)]) -> RunService:
    return RunService(RunRepository(session))


Service = Annotated[RunService, Depends(get_run_service)]


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, service: Service) -> RunRead:
    run = await service.create(payload)
    await enqueue_plan(run.id)
    return run


@router.get("")
async def list_runs(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    return await service.list(limit, offset)


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: UUID, service: Service) -> RunRead:
    return await service.read(await service.require(run_id))


@router.get("/{run_id}/export")
async def export_run(run_id: UUID, service: Service, format: ExportFormat = "json") -> Response:
    run = await service.read(await service.require(run_id))
    content, media_type = await export_result(run, format)
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}.{format}"',
        },
    )


@router.get("/{run_id}/files", response_model=list[ContextFileRead])
async def list_run_files(run_id: UUID, service: Service) -> list[ContextFileRead]:
    return await service.files(run_id)


@router.patch("/{run_id}/plan", response_model=RunRead)
async def update_run_plan(run_id: UUID, payload: RunPlanUpdate, service: Service) -> RunRead:
    return await service.update_plan(run_id, payload)


@router.post("/{run_id}/confirm", response_model=RunRead)
async def confirm_run(run_id: UUID, service: Service) -> RunRead:
    run = await service.confirm(run_id)
    await enqueue_run(run.id)
    return run


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: UUID, service: Service) -> RunRead:
    return await service.cancel(run_id)


@router.post("/{run_id}/steps/{step_number}/retry", response_model=RunRead)
async def retry_step(run_id: UUID, step_number: int, service: Service) -> RunRead:
    run = await service.retry(run_id, step_number)
    await enqueue_run(run.id)
    return run
