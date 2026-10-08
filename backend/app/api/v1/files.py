"""Run file upload and download API routes."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.file_repository import FileRepository
from app.db.session import get_session
from app.schemas.context_file import ContextFileRead
from app.services.files import FileService

router = APIRouter()


def get_file_service(session: Annotated[AsyncSession, Depends(get_session)]) -> FileService:
    return FileService(FileRepository(session))


Service = Annotated[FileService, Depends(get_file_service)]


@router.post("", response_model=ContextFileRead, status_code=201)
async def upload_file(file: UploadFile, service: Service) -> ContextFileRead:
    try:
        content = await file.read(get_settings().context_file_max_bytes + 1)
        return await service.upload(file.filename or "", file.content_type or "", content)
    finally:
        await file.close()


@router.get("/{file_id}", response_model=ContextFileRead)
async def get_file(file_id: UUID, service: Service) -> ContextFileRead:
    return ContextFileRead.model_validate(await service.require(file_id))


@router.get("/{file_id}/download")
async def download_file(file_id: UUID, service: Service) -> Response:
    file = await service.require(file_id)
    return Response(
        file.content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: UUID, service: Service) -> Response:
    await service.delete(file_id)
    return Response(status_code=204)
