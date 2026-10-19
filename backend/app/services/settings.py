"""Read and update public configuration without modifying server secrets."""

from app.core.config import Settings
from app.core.errors import AppError
from app.db.model_repository import ModelRepository
from app.db.settings_repository import SettingsRepository
from app.llm.registry import get_model_registry
from app.schemas.settings import AgentDefaults, AppConfigRead
from app.services.models import ModelService, ModelUnavailable


class SettingsError(AppError):
    code = "invalid_agent_defaults"
    status_code = 422


class SettingsService:
    def __init__(self, repository: SettingsRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def validate(self, defaults: AgentDefaults) -> None:
        model = get_model_registry(self.settings).get(defaults.default_model)
        if model is None or defaults.max_tokens > min(
            model.context_window, model.max_output_tokens
        ):
            raise SettingsError("Choose a registered model and a supported token limit.")

    def public(self, defaults: AgentDefaults) -> AppConfigRead:
        settings = self.settings
        return AppConfigRead(
            **defaults.model_dump(),
            llm_provider_mode=settings.llm_provider_mode,
            code_executor_backend=settings.code_executor_backend,
            anthropic_key_configured=bool(settings.anthropic_api_key),
            openai_key_configured=bool(settings.openai_api_key),
            tavily_key_configured=bool(settings.tavily_api_key),
        )

    async def read(self) -> AppConfigRead:
        stored = await self.repository.read()
        defaults = (
            AgentDefaults.model_validate(stored)
            if stored
            else AgentDefaults(
                default_model=self.settings.default_agent_model,
                temperature=self.settings.default_agent_temperature,
                max_tokens=self.settings.default_agent_max_tokens,
            )
        )
        self.validate(defaults)
        return self.public(defaults)

    async def update(self, defaults: AgentDefaults) -> AppConfigRead:
        self.validate(defaults)
        if (
            defaults.default_model
            not in await ModelService(
                ModelRepository(self.repository.session), self.settings
            ).available()
        ):
            raise ModelUnavailable("Choose an enabled default model from a connected provider.")
        await self.repository.save(defaults.model_dump())
        return self.public(defaults)
