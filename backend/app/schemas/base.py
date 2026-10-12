"""Reject text that PostgreSQL cannot store before it reaches persistence."""

from pydantic import BaseModel, model_validator


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
