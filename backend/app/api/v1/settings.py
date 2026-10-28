"""Application settings endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.model_repository import ModelRepository
from app.db.session import get_session
from app.db.settings_repository import SettingsRepository
from app.schemas.model_setting import ModelCatalogue, ModelSwitch
from app.schemas.settings import AppConfigRead, AppConfigUpdate
from app.services.models import ModelService
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
async def update_config(payload: AppConfigUpdate, service: Service) -> AppConfigRead:
    return await service.update(payload)


def get_model_service(session: Annotated[AsyncSession, Depends(get_session)]) -> ModelService:
    return ModelService(ModelRepository(session))


Models = Annotated[ModelService, Depends(get_model_service)]


@router.get("/models", response_model=ModelCatalogue)
async def get_models(service: Models) -> ModelCatalogue:
    return await service.catalogue()


@router.patch("/models/{key}", response_model=ModelCatalogue)
async def update_model(key: str, payload: ModelSwitch, service: Models) -> ModelCatalogue:
    return await service.update(key, payload.enabled)
