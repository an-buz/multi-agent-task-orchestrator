"""Unit tests for workflow graph validation."""

from uuid import uuid4

from app.schemas.workflow import WorkflowWrite, validate_workflow_graph


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
