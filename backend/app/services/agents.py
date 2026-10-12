"""Agent validation and CRUD rules independent of HTTP."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.db.agent_repository import AgentRepository
from app.llm.registry import TOOLS, get_model_registry
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate


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
        elif payload.max_tokens > model.context_window:
            details = {"field": "max_tokens", "reason": "exceeds_model_context_window"}
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
        return AgentRead.model_validate(agent)

    async def create(self, payload: AgentCreate) -> AgentRead:
        self.validate(payload)
        return await self.persist(Agent(**payload.model_dump()))

    async def read(self, agent_id: str) -> AgentRead:
        return AgentRead.model_validate(await self.require(agent_id))

    async def update(self, agent_id: str, payload: AgentUpdate) -> AgentRead:
        agent = await self.require(agent_id)
        self.validate(payload)
        for field, value in payload.model_dump().items():
            setattr(agent, field, value)
        return await self.persist(agent)

    async def delete(self, agent_id: str) -> None:
        await self.repository.delete(await self.require(agent_id))

    async def list(self, limit: int, offset: int) -> dict[str, object]:
        agents, total = await self.repository.list(limit, offset)
        return {"items": [AgentRead.model_validate(agent) for agent in agents], "total": total}
