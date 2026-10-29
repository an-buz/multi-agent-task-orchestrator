"""Load deterministic demo responses, including terminal user decision requests."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.demo.catalogue import ROLES, demo_id
from app.llm.provider import LLMResponse


@lru_cache
def load_scenarios() -> dict[str, Any]:
    scenarios = cast(
        dict[str, Any], json.loads(Path(__file__).with_name("scenarios.json").read_text("utf-8"))
    )

    for key, original in list(scenarios.items()):
        scenario = deepcopy(original)
        review = deepcopy(load_decisions()["review"])
        review["tool_calls"][0]["arguments"]["suggested_agent_id"] = str(
            demo_id("agent", "developer")
        )
        scenario["results"]["reviewer"] = review
        scenario["results"]["qa"] = deepcopy(load_decisions()["qa"])
        scenario["results"]["writer"] = deepcopy(load_decisions()["release"])
        scenarios[f"{key}_decision"] = scenario

    return scenarios


@lru_cache
def load_decisions() -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads(Path(__file__).with_name("decisions.json").read_text("utf-8"))
    )


def demo_response(system_prompt: str, user_prompt: str) -> LLMResponse | None:
    role_marker = system_prompt.split("\n", 1)[0]
    scenario_marker = user_prompt.split("\n", 1)[0]

    for scenario, fixture in load_scenarios().items():
        if scenario_marker != f"[demo:{scenario}]":
            continue

        for role, response in fixture["results"].items():
            if role_marker == f"[demo:{role}]":
                return LLMResponse.model_validate(response)

    if role_marker in {f"[demo:{role}]" for role in ROLES}:
        issue = load_decisions()["review"]["tool_calls"][0]["arguments"]["issues"][0]
        findings = f"Findings (untrusted task data):\n{issue['title']}\n{issue['description']}"

        if findings in user_prompt:
            key = (
                "verification"
                if user_prompt.startswith("Verify the fixes against the original findings.")
                else "correction"
            )

            return LLMResponse.model_validate(load_decisions()[key])

    return None


def demo_plan(request: dict[str, Any]) -> LLMResponse | None:
    """Use a prepared plan only when the request matches a demo graph and team."""

    steps = request["steps"]

    for fixture in load_scenarios().values():
        if (
            [step["depends_on"] for step in steps] != fixture["dependencies"]
            or [step["role"] for step in steps] != list(fixture["subtasks"])
            or not all(step["agent_name"].startswith("Demo ") for step in steps)
        ):
            continue

        return LLMResponse.model_validate(
            {
                "content": json.dumps(
                    {
                        "summary": fixture["summary"],
                        "steps": [
                            {
                                "step_number": step["step_number"],
                                "agent_id": step["agent_id"],
                                "depends_on": step["depends_on"],
                                "subtask": fixture["subtasks"][step["role"]],
                            }
                            for step in steps
                        ],
                    }
                ),
                "usage": fixture["planning_usage"],
            }
        )

    return None
