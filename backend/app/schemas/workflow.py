"""Workflow API schemas and graph validation."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

WorkflowType = Literal["sequential", "parallel", "hybrid"]


class WorkflowStepInput(BaseModel):
    step_number: int = Field(ge=1)
    agent_id: UUID
    depends_on: list[int] = Field(default_factory=list)
    input_transform: str = ""


class WorkflowWrite(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    execution_type: WorkflowType
    steps: list[WorkflowStepInput] = Field(min_length=1, max_length=100)
    graph_layout: dict[str, Any] = Field(default_factory=dict)


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    execution_type: WorkflowType
    steps: list[WorkflowStepInput]
    graph_layout: dict[str, Any]
    created_at: datetime
    updated_at: datetime


def validate_workflow_graph(payload: WorkflowWrite) -> list[str]:
    """Return graph validation errors without accessing persistence."""
    errors: list[str] = []
    numbers = [step.step_number for step in payload.steps]
    if len(numbers) != len(set(numbers)):
        errors.append("step_number values must be unique")
    known = set(numbers)
    for step in payload.steps:
        if step.step_number in step.depends_on:
            errors.append(f"step {step.step_number} cannot depend on itself")
        if len(step.depends_on) != len(set(step.depends_on)):
            errors.append(f"step {step.step_number} has duplicate dependencies")
        for dependency in step.depends_on:
            if dependency not in known:
                errors.append(f"step {step.step_number} depends on missing step {dependency}")

    dependencies = {step.step_number: set(step.depends_on) for step in payload.steps}
    remaining = {number: set(values) for number, values in dependencies.items()}
    ready = [number for number, values in remaining.items() if not values]
    visited = 0
    processed: set[int] = set()
    while ready:
        number = ready.pop()
        if number in processed:
            continue
        processed.add(number)
        visited += 1
        for target, values in remaining.items():
            values.discard(number)
            if not values and target not in ready and target not in processed:
                ready.append(target)
    if visited != len(numbers):
        errors.append("workflow graph must be acyclic")

    if payload.execution_type == "sequential":
        ordered = sorted(payload.steps, key=lambda step: step.step_number)
        if any(
            step.depends_on != ([] if index == 0 else [ordered[index - 1].step_number])
            for index, step in enumerate(ordered)
        ):
            errors.append("sequential workflows must form a single ordered chain")
    if payload.execution_type == "parallel":
        aggregators = [step for step in payload.steps if step.depends_on]
        if (
            any(step.depends_on for step in payload.steps if step not in aggregators)
            or len(aggregators) > 1
        ):
            errors.append("parallel workflows may have independent steps and one final aggregator")
        if aggregators and set(aggregators[0].depends_on) != known - {aggregators[0].step_number}:
            errors.append("parallel aggregator must depend on every other step")
    return errors
