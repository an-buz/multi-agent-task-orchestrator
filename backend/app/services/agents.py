"""Agent validation and CRUD rules independent of HTTP."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.db.agent_repository import AgentRepository
from app.db.model_repository import ModelRepository
from app.llm.registry import TOOLS, get_model_registry
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.services.models import ModelService, ModelUnavailable


class AgentError(AppError):
    def __init__(
        self, message: str, code: str, status_code: int, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message, details)

        self.code = code
        self.status_code = status_code


class AgentService:
    def __init__(self, repository: AgentRepository) -> None:
        self.repository = repository

    def validate(self, payload: AgentCreate | AgentUpdate) -> None:
        model = get_model_registry().get(payload.model)

        details: dict[str, object] = {}

        if model is None:
            details = {"field": "model", "reason": "unknown_model"}
        elif payload.max_tokens > model.max_output_tokens:
            details = {"field": "max_tokens", "reason": "exceeds_model_output_limit"}
        elif payload.context_window > model.context_window:
            details = {"field": "context_window", "reason": "exceeds_model_context_window"}
        elif payload.max_tokens >= payload.context_window:
            details = {"field": "max_tokens", "reason": "must_leave_room_for_input"}
        else:
            invalid_tools = sorted(set(payload.tools) - TOOLS.keys())

            if invalid_tools:
                details = {"field": "tools", "reason": "unknown_tools", "tools": invalid_tools}

        if details:
            raise AgentError("Invalid agent configuration.", "invalid_agent", 422, details)

    async def require(self, agent_id: str) -> Agent:
        try:
            parsed_id = UUID(agent_id)
        except ValueError as exception:
            raise AgentError("Agent not found", "agent_not_found", 404) from exception

        agent = await self.repository.get(parsed_id)

        if agent is None:
            raise AgentError("Agent not found", "agent_not_found", 404)

        return agent

    async def persist(self, agent: Agent) -> AgentRead:
        try:
            await self.repository.save(agent)
        except IntegrityError as exception:
            await self.repository.rollback()

            raise AgentError(
                "An agent with this name already exists.", "duplicate_agent_name", 409
            ) from exception

        return await self.representation(agent)

    async def representation(self, agent: Agent, available: set[str] | None = None) -> AgentRead:
        value = AgentRead.model_validate(agent)
        value.available = not agent.requires_reconfiguration and agent.model in (
            available
            if available is not None
            else await ModelService(ModelRepository(self.repository.session)).available()
        )

        return value

    async def validate_availability(self, model: str) -> None:
        if model not in await ModelService(ModelRepository(self.repository.session)).available():
            raise ModelUnavailable("Choose an enabled model from a connected provider.")

    async def create(self, payload: AgentCreate) -> AgentRead:
        self.validate(payload)

        await self.validate_availability(payload.model)

        return await self.persist(Agent(**payload.model_dump(), requires_reconfiguration=False))

    async def read(self, agent_id: str) -> AgentRead:
        return await self.representation(await self.require(agent_id))

    async def update(self, agent_id: str, payload: AgentUpdate) -> AgentRead:
        agent = await self.require(agent_id)

        self.validate(payload)

        await self.validate_availability(payload.model)

        for field, value in payload.model_dump().items():
            setattr(agent, field, value)

        agent.requires_reconfiguration = False

        return await self.persist(agent)

    async def delete(self, agent_id: str) -> None:
        await self.repository.delete(await self.require(agent_id))

    async def list(self, limit: int, offset: int) -> dict[str, object]:
        # Keep policy stable while reading agents, without resolving it for each row.
        available = await ModelService(ModelRepository(self.repository.session)).available()
        agents, total = await self.repository.list(limit, offset)

        return {
            "items": [await self.representation(agent, available) for agent in agents],
            "total": total,
        }
