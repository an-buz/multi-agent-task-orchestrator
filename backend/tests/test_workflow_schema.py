"""Unit tests for workflow graph validation."""

from uuid import uuid4

import pytest
from app.llm.planning import PlannedSubtask
from app.schemas.run import RunPlanStep
from app.schemas.workflow import (
    WorkflowStepInput,
    WorkflowStepRead,
    WorkflowWrite,
    validate_workflow_graph,
)
from pydantic import ValidationError


@pytest.mark.parametrize("field", ["step_number", "depends_on"])
def test_legacy_workflow_identifiers_are_readable_but_cannot_be_written(field: str) -> None:
    payload = {"step_number": 1, "agent_id": uuid4(), "depends_on": []}
    payload[field] = 2147483648 if field == "step_number" else [2147483648]
    read = WorkflowStepRead.model_validate(payload)
    assert getattr(read, field) == payload[field]
    with pytest.raises(ValidationError):
        WorkflowStepInput.model_validate(read.model_dump())


def test_valid_hybrid_dag_passes() -> None:
    agent_id = uuid4()
    payload = WorkflowWrite.model_validate(
        {
            "title": "Research",
            "execution_type": "hybrid",
            "steps": [
                {"step_number": 1, "agent_id": agent_id},
                {"step_number": 2, "agent_id": agent_id, "depends_on": [1]},
                {"step_number": 3, "agent_id": agent_id, "depends_on": [1]},
                {"step_number": 4, "agent_id": agent_id, "depends_on": [2, 3]},
            ],
        }
    )
    assert validate_workflow_graph(payload) == []


def test_cycle_is_rejected() -> None:
    agent_id = uuid4()
    payload = WorkflowWrite.model_validate(
        {
            "title": "Cycle",
            "execution_type": "hybrid",
            "steps": [
                {"step_number": 1, "agent_id": agent_id, "depends_on": [2]},
                {"step_number": 2, "agent_id": agent_id, "depends_on": [1]},
            ],
        }
    )
    assert "workflow graph must be acyclic" in validate_workflow_graph(payload)


def test_sequential_requires_a_single_chain() -> None:
    agent_id = uuid4()
    payload = WorkflowWrite.model_validate(
        {
            "title": "Broken chain",
            "execution_type": "sequential",
            "steps": [
                {"step_number": 1, "agent_id": agent_id},
                {"step_number": 2, "agent_id": agent_id},
            ],
        }
    )
    assert "sequential workflows must form a single ordered chain" in validate_workflow_graph(
        payload
    )


@pytest.mark.parametrize("schema", [RunPlanStep, PlannedSubtask])
@pytest.mark.parametrize("field", ["step_number", "depends_on"])
@pytest.mark.parametrize("number", [0, 2147483648])
def test_plan_identifiers_match_postgres_range(schema, field: str, number: int) -> None:
    payload = {"step_number": 1, "depends_on": [], "agent_id": uuid4(), "subtask": "Review"}
    if schema is RunPlanStep:
        payload["agent_name"] = "Reviewer"
    payload[field] = number if field == "step_number" else [number]
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize("field", ["step_number", "depends_on"])
@pytest.mark.parametrize("number", [0, 2147483648])
def test_workflow_identifiers_match_postgres_range(field: str, number: int) -> None:
    step = {"step_number": 1, "agent_id": uuid4(), "depends_on": []}
    step[field] = number if field == "step_number" else [number]
    with pytest.raises(ValidationError):
        WorkflowWrite.model_validate(
            {"title": "Bounds", "execution_type": "hybrid", "steps": [step]}
        )
