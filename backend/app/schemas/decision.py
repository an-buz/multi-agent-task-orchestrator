"""Validated agent findings and explicit human decisions."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from app.schemas.base import StepNumber, StorageModel

DecisionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
]


class Finding(StorageModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    description: DecisionText
    severity: Literal["low", "medium", "high", "critical"]


class DecisionRequest(StorageModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[Finding] = Field(min_length=1, max_length=20)
    suggested_agent_id: UUID | None = None
    suggested_task: DecisionText


class DecisionResolution(StorageModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["assign_fixes", "continue", "cancel"]
    agent_id: UUID | None = None
    task: DecisionText | None = None
    comment: Annotated[str, StringConstraints(max_length=10000)] = ""

    @model_validator(mode="after")
    def validate_assignment(self) -> DecisionResolution:
        if self.action == "assign_fixes" and (self.agent_id is None or self.task is None):
            raise ValueError("Assigning fixes requires an agent and task.")

        if self.action != "assign_fixes" and (self.agent_id is not None or self.task is not None):
            raise ValueError("Only an assignment may specify an agent and task.")

        return self


class DecisionRead(DecisionRequest):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_step_number: StepNumber
    status: Literal["PENDING", "RESOLVED"]
    resolution: DecisionResolution | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    followup_step_numbers: list[StepNumber] = Field(default_factory=list)


def decision_tool() -> dict[str, object]:
    return {
        "name": "request_user_decision",
        "description": (
            "When you discover problems requiring another agent's work, call this tool to "
            "finish your review and pause the workflow for the user's decision. Include concrete "
            "findings and a proposed fix task. This is a terminal control request: call it alone, "
            "without other tools in the same response. Do not fix, delegate, or grant permissions "
            "yourself. Put your review report in the response text."
        ),
        "input_schema": DecisionRequest.model_json_schema(),
    }
