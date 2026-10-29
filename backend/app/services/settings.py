"""Read and update public configuration without modifying server secrets."""

from app.core.config import Settings
from app.core.errors import AppError
from app.db.model_repository import ModelRepository
from app.db.settings_repository import SettingsRepository
from app.llm.discovery import refresh_model_registry
from app.llm.registry import get_model_registry
from app.schemas.settings import AgentDefaults, AppConfigRead, AppConfigUpdate
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

        if model is None or any(
            defaults.max_tokens > limit
            for limit in (model.context_window, model.max_output_tokens)
            if limit is not None
        ):
            raise SettingsError("Choose a registered model and a supported token limit.")

    def public(self, defaults: AgentDefaults, planner_model: str) -> AppConfigRead:
        settings = self.settings

        return AppConfigRead(
            **defaults.model_dump(exclude={"planner_model"}),
            planner_model=planner_model,
            llm_provider_mode=settings.llm_provider_mode,
            code_executor_backend=settings.code_executor_backend,
            anthropic_key_configured=bool(settings.anthropic_api_key),
            openai_key_configured=bool(settings.openai_api_key),
            gemini_key_configured=bool(settings.gemini_api_key),
            tavily_key_configured=bool(settings.tavily_api_key),
        )

    async def read(self) -> AppConfigRead:
        stored = await self.repository.read()

        defaults = (
            AppConfigUpdate.model_validate(stored)
            if stored
            else AppConfigUpdate(
                default_model=self.settings.default_agent_model,
                temperature=self.settings.default_agent_temperature,
                max_tokens=self.settings.default_agent_max_tokens,
            )
        )

        return self.public(defaults, defaults.planner_model or self.settings.planner_model)

    async def resolve_planner_model(self) -> str:
        """Read fresh persisted selection for a new Run, with environment fallback."""

        stored = await self.repository.read()

        model = stored.get("planner_model") if stored else None

        return model if isinstance(model, str) else self.settings.planner_model

    async def update(self, defaults: AppConfigUpdate) -> AppConfigRead:
        await refresh_model_registry(self.settings)

        self.validate(defaults)

        available = await ModelService(
            ModelRepository(self.repository.session), self.settings
        ).available()

        if defaults.default_model not in available:
            raise ModelUnavailable("Choose an enabled default model from a connected provider.")

        if defaults.planner_model is not None:
            if defaults.planner_model not in available:
                raise ModelUnavailable("Choose an enabled planner model from a connected provider.")

            info = get_model_registry(self.settings)[defaults.planner_model]

            if (
                info.max_output_tokens is not None
                and self.settings.planner_max_tokens > info.max_output_tokens
            ):
                raise SettingsError("The planner token limit exceeds this model's output limit.")

        # Legacy clients omit planner_model; the atomic JSON merge preserves its value.
        await self.repository.save(defaults.model_dump(exclude_none=True))

        return await self.read()
