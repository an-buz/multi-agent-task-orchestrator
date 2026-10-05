"""Agent creation and catalogue routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.llm.registry import TOOLS, get_model_registry
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate

router = APIRouter()


@router.get("")
async def list_agents(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    """Return persisted agents in reverse creation order."""
    total = await session.scalar(select(func.count()).select_from(Agent))
    result = await session.scalars(
        select(Agent).order_by(Agent.created_at.desc(), Agent.name).limit(limit).offset(offset)
    )
    return {
        "items": [AgentRead.model_validate(agent).model_dump(mode="json") for agent in result],
        "total": total or 0,
    }


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Agent:
    """Validate and persist an agent."""
    await validate_agent_payload(payload)
    agent = Agent(**payload.model_dump())
    session.add(agent)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_agent_name",
                "message": "An agent with this name already exists.",
            },
        ) from exc
    await session.refresh(agent)
    return agent


async def validate_agent_payload(payload: AgentCreate | AgentUpdate) -> None:
    """Validate model limits and allowed tools against configured catalogues."""
    model = get_model_registry().get(payload.model)
    if model is None:
        raise HTTPException(status_code=422, detail={"field": "model", "reason": "unknown_model"})
    if payload.max_tokens > model.context_window:
        raise HTTPException(
            status_code=422,
            detail={"field": "max_tokens", "reason": "exceeds_model_context_window"},
        )
    if payload.context_window > model.context_window:
        raise HTTPException(
            status_code=422,
            detail={"field": "context_window", "reason": "exceeds_model_context_window"},
        )
    invalid_tools = sorted(set(payload.tools) - TOOLS.keys())
    if invalid_tools:
        raise HTTPException(
            status_code=422,
            detail={"field": "tools", "reason": "unknown_tools", "tools": invalid_tools},
        )


@router.get("/models")
async def list_models() -> dict[str, list[dict[str, str | int]]]:
    """Return model aliases accepted by agent creation and their limits."""
    return {
        "items": [
            {
                "key": model.key,
                "provider": model.provider,
                "model_id": model.model_id,
                "tier": model.tier,
                "context_window": model.context_window,
            }
            for model in get_model_registry().values()
        ]
    }


@router.get("/tools")
async def list_tools() -> dict[str, list[dict[str, str]]]:
    """Return the safe MVP tool catalogue."""
    return {"items": [tool.__dict__ for tool in TOOLS.values()]}


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> Agent:
    """Return one saved agent."""
    from uuid import UUID

    try:
        parsed_id = UUID(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    agent = await session.get(Agent, parsed_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Agent:
    """Replace an agent configuration."""
    from uuid import UUID

    try:
        parsed_id = UUID(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    agent = await session.get(Agent, parsed_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    await validate_agent_payload(payload)
    for field, value in payload.model_dump().items():
        setattr(agent, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_agent_name",
                "message": "An agent with this name already exists.",
            },
        ) from exc
    await session.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> None:
    """Delete one saved agent."""
    from uuid import UUID

    try:
        parsed_id = UUID(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Agent not found") from exc
    agent = await session.get(Agent, parsed_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    await session.delete(agent)
    await session.commit()
