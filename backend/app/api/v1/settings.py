"""Application settings endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.db.settings_repository import SettingsRepository
from app.schemas.settings import AgentDefaults, AppConfigRead
from app.services.settings import SettingsService

router = APIRouter()


def get_settings_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SettingsService:
    return SettingsService(SettingsRepository(session), settings)


Service = Annotated[SettingsService, Depends(get_settings_service)]


@router.get("/config", response_model=AppConfigRead)
async def get_config(service: Service) -> AppConfigRead:
    return await service.read()


@router.patch("/config", response_model=AppConfigRead)
async def update_config(payload: AgentDefaults, service: Service) -> AppConfigRead:
    return await service.update(payload)
