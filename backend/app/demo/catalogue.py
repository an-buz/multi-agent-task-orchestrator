"""Repeatable demo data, isolated from the user's regular database by the launcher."""

from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.registry import get_model_registry
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.schemas.agent import AgentCreate
from app.schemas.workflow import WorkflowStepInput, WorkflowWrite, validate_workflow_graph

ROLES = ("analyst", "developer", "qa", "reviewer", "writer")
NAMES = ("Analyst", "Developer", "QA", "Reviewer", "Technical Writer")
DEPENDENCIES: dict[str, list[list[int]]] = {
    "sequential": [[], [1], [2], [3], [4]],
    "parallel": [[], [], [], [], [1, 2, 3, 4]],
    "hybrid": [[], [1], [1], [2, 3], [4]],
}
POSITIONS = {
    "sequential": [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],
    "parallel": [(0, 0), (0, 1), (0, 2), (0, 3), (1, 1)],
    "hybrid": [(0, 0), (1, 0), (1, 1), (2, 0), (3, 0)],
}
DEMO_TASK = "Prepare the task board release with task creation, status filters, and release notes."


def demo_id(kind: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"orchestrator/demo/v1/{kind}/{key}")


def agent_payloads(settings: Settings) -> list[AgentCreate]:
    model = get_model_registry(settings)[settings.default_agent_model]

    return [
        AgentCreate(
            name=f"Demo {name}",
            role=role,
            system_prompt=(
                f"[demo:{role}]\nYou are the {name} in a simulated task board release team. "
                "Produce a concrete Markdown handoff. All implementation, checks, and findings "
                "are fictional demonstration data; do not call external tools."
            ),
            model=model.key,
            temperature=settings.default_agent_temperature,
            max_tokens=settings.default_agent_max_tokens,
            context_window=model.context_window,
            tools=[],
        )
        for role, name in zip(ROLES, NAMES, strict=True)
    ]


def workflow_payloads(*, with_decisions: bool = False) -> list[WorkflowWrite]:
    payloads: list[WorkflowWrite] = []

    for execution_type, dependencies in DEPENDENCIES.items():
        scenario = f"{execution_type}_decision" if with_decisions else execution_type
        steps = []

        for number, (role, parents) in enumerate(zip(ROLES, dependencies, strict=True), 1):
            template = (
                f"[demo:{scenario}]\nTask: {{{{task}}}}\n"
                "Subtask: {{subtask}}\nContext: {{context}}"
            )

            for parent in parents:
                template += f"\n\nStep {parent}:\n{{{{steps.{parent}.output}}}}"

            steps.append(
                WorkflowStepInput(
                    step_number=number,
                    agent_id=demo_id("agent", role),
                    depends_on=parents,
                    input_transform=template,
                )
            )

        payload = WorkflowWrite.model_validate(
            {
                "title": f"Demo: Task board release ({execution_type})"
                + (" with user decision" if with_decisions else ""),
                "execution_type": execution_type,
                "steps": steps,
                "graph_layout": {
                    str(number): {
                        "x": 80 + column * 280,
                        "y": 80 + row * 170,
                    }
                    for number, (column, row) in enumerate(POSITIONS[execution_type], 1)
                },
            }
        )

        if errors := validate_workflow_graph(payload):
            raise ValueError(errors)

        payloads.append(payload)

    return payloads


async def seed_demo(session: AsyncSession, settings: Settings) -> None:
    """Insert missing demo records atomically; preserve edits and previous runs."""

    if not settings.demo_mode:
        raise ValueError("Seeding requires DEMO_MODE=true")

    # Serialize concurrent starts so they cannot insert the same catalogue twice.
    await session.execute(text("SELECT pg_advisory_xact_lock(41892361)"))

    for role, payload in zip(ROLES, agent_payloads(settings), strict=True):
        agent_id = demo_id("agent", role)

        if await session.get(Agent, agent_id) is None:
            existing = await session.scalar(select(Agent.id).where(Agent.name == payload.name))

            if existing is not None:
                raise ValueError(f"Demo agent name is already used: {payload.name}")

            session.add(Agent(id=agent_id, **payload.model_dump(), requires_reconfiguration=False))

    await session.flush()

    for with_decisions in (False, True):
        for workflow in workflow_payloads(with_decisions=with_decisions):
            key = workflow.execution_type + ("_decision" if with_decisions else "")
            workflow_id = demo_id("workflow", key)

            if await session.get(Workflow, workflow_id) is None:
                session.add(Workflow(id=workflow_id, **workflow.model_dump(mode="json")))

    await session.commit()
