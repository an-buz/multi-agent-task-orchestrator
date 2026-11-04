"""Copy saved agent configuration into an independent execution snapshot."""

from dataclasses import asdict
from typing import Any

from app.llm.registry import get_model_registry
from app.models.agent import Agent


def snapshot_agent(agent: Agent) -> dict[str, Any]:
    info = get_model_registry().get(agent.model)

    return {
        "model_info": asdict(info) if info is not None else None,
        "role": agent.role,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "context_window": agent.context_window,
        "tools": list(agent.tools),
    }
