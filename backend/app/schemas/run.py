"""Run creation, planning, and response schemas."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RunStatus = Literal[
    "PLANNING",
    "AWAITING_CONFIRMATION",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]
StepStatus = Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"]


class RunCreate(BaseModel):
    """Input for a new workflow run."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: UUID
    task: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    context_text: str = ""


class RunPlanStep(BaseModel):
    """A planned workflow step, ready for user review."""

    step_number: int = Field(ge=1)
    agent_id: UUID
    agent_name: str
    subtask: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    status: StepStatus = "PENDING"
    depends_on: list[int] = Field(default_factory=list)
    input: str | None = None
    output: str | None = None
    error: dict[str, str] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    attempt: int = 0


class RunPlan(BaseModel):
    """Human-readable strategy and per-agent subtasks."""

    summary: str
    steps: list[RunPlanStep]


class RunPlanUpdate(BaseModel):
    """Edited subtasks submitted from Plan Preview."""

    steps: list[RunPlanStep] = Field(min_length=1, max_length=100)


class RunRead(BaseModel):
    """Public run representation consumed by the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    workflow_title: str
    task: str
    context_text: str
    status: RunStatus
    plan: RunPlan
    final_report: str | None
    total_tokens: int
    total_time_ms: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
