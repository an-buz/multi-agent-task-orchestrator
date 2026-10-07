"""Public SSE envelope; payload names follow the API event contract."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from app.schemas.run import RunPlan, RunRead, StepStatus

EventName = Literal[
    "plan:ready",
    "task:started",
    "agent:status_change",
    "agent:completed",
    "agent:failed",
    "task:finished",
    "task:failed",
    "task:cancelled",
    "run:snapshot",
]


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanReady(EventData):
    plan: RunPlan


class TaskIdentity(EventData):
    taskId: UUID


class TaskStarted(TaskIdentity):
    workflowId: UUID


class StepIdentity(EventData):
    agentId: UUID
    stepNumber: int


class StatusChanged(StepIdentity):
    status: StepStatus


class TokenUsage(EventData):
    prompt: int
    completion: int
    total: int


class StepCompleted(StepIdentity):
    output: str
    tokensUsed: TokenUsage
    executionTime: float


class StepError(EventData):
    code: str
    message: str


class StepFailed(StepIdentity):
    error: StepError
    retryable: bool


class TaskFinished(TaskIdentity):
    finalReport: str
    totalTokens: int
    totalTimeMs: int


class TaskFailed(TaskIdentity):
    failedSteps: list[int]


class Snapshot(EventData):
    run: RunRead


PAYLOAD_MODELS: dict[str, type[EventData]] = {
    "plan:ready": PlanReady,
    "task:started": TaskStarted,
    "agent:status_change": StatusChanged,
    "agent:completed": StepCompleted,
    "agent:failed": StepFailed,
    "task:finished": TaskFinished,
    "task:failed": TaskFailed,
    "task:cancelled": TaskIdentity,
    "run:snapshot": Snapshot,
}


class EventEnvelope(BaseModel):
    event: EventName
    runId: UUID
    ts: datetime
    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def validate_payload(cls, value: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        event = info.data.get("event")
        if event in PAYLOAD_MODELS:
            return PAYLOAD_MODELS[event].model_validate(value).model_dump(mode="json")
        return value
