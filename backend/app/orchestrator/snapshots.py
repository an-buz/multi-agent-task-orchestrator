"""Copy saved agent configuration into an independent execution snapshot."""

from typing import Any

from app.models.agent import Agent


def snapshot_agent(agent: Agent) -> dict[str, Any]:
    return {
        "role": agent.role,
        "system_prompt": agent.system_prompt,
        "model": agent.model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "context_window": agent.context_window,
        "tools": list(agent.tools),
    }
