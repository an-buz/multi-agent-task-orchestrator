"""Reject text that PostgreSQL cannot store before it reaches persistence."""

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

# RunStep.step_number is stored as a PostgreSQL signed INTEGER.
StepNumber = Annotated[int, Field(ge=1, le=2147483647)]


def validate_storage_text(value: object) -> object:
    """Check nested JSON strings without recursion or modifying their content."""

    pending = [value]

    while pending:
        item = pending.pop()

        if isinstance(item, str):
            if "\x00" in item:
                raise ValueError("Text must not contain null characters.")

            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exception:
                raise ValueError("Text must contain valid Unicode characters.") from exception
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list | tuple):
            pending.extend(item)

    return value


class StorageModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def validate_text(cls, value: object) -> object:
        return validate_storage_text(value)
