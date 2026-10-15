"""HTTP adapters for the agent catalogue."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.settings import Models
from app.db.agent_repository import AgentRepository
from app.db.session import get_session
from app.llm.registry import TOOLS
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from app.schemas.model_setting import ModelCatalogue
from app.services.agents import AgentService

router = APIRouter()


def get_agent_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AgentService:
    return AgentService(AgentRepository(session))


Service = Annotated[AgentService, Depends(get_agent_service)]


@router.get("")
async def list_agents(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    return await service.list(limit, offset)


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, service: Service) -> AgentRead:
    return await service.create(payload)


@router.get("/models")
async def list_models(service: Models) -> ModelCatalogue:
    return await service.catalogue(enabled_only=True)


@router.get("/tools")
async def list_tools() -> dict[str, list[dict[str, str]]]:
    return {"items": [tool.__dict__ for tool in TOOLS.values()]}


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: str, service: Service) -> AgentRead:
    return await service.read(agent_id)


@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(agent_id: str, payload: AgentUpdate, service: Service) -> AgentRead:
    return await service.update(agent_id, payload)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, service: Service) -> None:
    await service.delete(agent_id)
