"""Resolve connected providers and persistent agent model availability."""

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.model_repository import ModelRepository
from app.llm.registry import ModelInfo, get_model_registry
from app.schemas.model_setting import ModelCatalogue, ModelRead


def connected(model: ModelInfo, settings: Settings) -> bool:
    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
    }

    return settings.llm_provider_mode == "mock" or bool(keys[model.provider])


class ModelUnavailable(AppError):
    code = "model_unavailable"
    status_code = 422


class ModelService:
    def __init__(self, repository: ModelRepository, settings: Settings | None = None) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    async def available(self) -> set[str]:
        disabled = await self.repository.disabled()

        return {
            key
            for key, model in get_model_registry(self.settings).items()
            if key not in disabled and connected(model, self.settings)
        }

    async def catalogue(self, *, enabled_only: bool = False) -> ModelCatalogue:
        disabled = await self.repository.disabled()

        return ModelCatalogue(
            items=[
                ModelRead(**model.__dict__, enabled=key not in disabled)
                for key, model in get_model_registry(self.settings).items()
                if connected(model, self.settings) and (not enabled_only or key not in disabled)
            ]
        )

    async def update(self, key: str, enabled: bool) -> ModelCatalogue:
        model = get_model_registry(self.settings).get(key)

        if model is None or not connected(model, self.settings):
            raise ModelUnavailable("This model does not belong to a connected provider.")

        await self.repository.set_enabled(key, enabled)

        return await self.catalogue()
