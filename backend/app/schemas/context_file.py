"""Public attachment metadata; content is downloaded separately."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContextFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    media_type: str
    size_bytes: int
    created_at: datetime
