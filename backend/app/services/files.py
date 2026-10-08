"""Bounded text validation and immutable context assembly, independent of HTTP."""

import json
from pathlib import PurePosixPath
from uuid import UUID

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.file_repository import FileRepository
from app.models.context_file import ContextFile
from app.schemas.context_file import ContextFileRead


class FileError(AppError):
    code = "invalid_context_file"

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_text_file(filename: str, media_type: str, content: bytes) -> tuple[str, str, str]:
    settings = get_settings()
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise FileError("Invalid filename.")
    extension = PurePosixPath(name).suffix.lower()
    types = {".txt": "text/plain", ".md": "text/markdown", ".json": "application/json"}
    if extension not in types:
        raise FileError("Only TXT, MD and JSON context files are supported.")
    mime = media_type.split(";", 1)[0].strip().lower()
    allowed = {types[extension], "application/octet-stream"}
    if extension in {".md", ".json"}:
        allowed.add("text/plain")
    if mime not in allowed:
        raise FileError("The file MIME type does not match its extension.")
    if len(content) > settings.context_file_max_bytes:
        raise FileError("The context file exceeds the upload limit.", 413)
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exception:
        raise FileError("Context files must use UTF-8 encoding.") from exception
    if not decoded.strip() or any(ord(char) < 32 and char not in "\n\r\t" for char in decoded):
        raise FileError("The file must contain non-empty text without binary control characters.")
    if extension == ".json":
        try:
            json.loads(decoded, parse_constant=reject_constant)
        except (ValueError, RecursionError) as exception:
            raise FileError("The context file contains invalid JSON.") from exception
    return name, types[extension], decoded


def reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


class FileService:
    def __init__(self, repository: FileRepository) -> None:
        self.repository = repository

    async def require(self, file_id: UUID, *, lock: bool = False) -> ContextFile:
        file = await self.repository.get(file_id, lock=lock)
        if file is None:
            raise FileError("Context file not found.", 404)
        return file

    async def upload(self, filename: str, media_type: str, content: bytes) -> ContextFileRead:
        name, mime, decoded = validate_text_file(filename, media_type, content)
        file = ContextFile(
            filename=name,
            media_type=mime,
            size_bytes=len(content),
            content=content,
            text_content=decoded,
        )
        await self.repository.save(file)
        return ContextFileRead.model_validate(file)

    async def delete(self, file_id: UUID) -> None:
        file = await self.require(file_id, lock=True)
        if await self.repository.is_attached(file_id):
            raise FileError("Files attached to a run cannot be deleted.", 409)
        await self.repository.delete(file)

    async def context(self, text: str, file_ids: list[UUID]) -> str:
        parts = [text] if text else []
        # Stable lock order prevents deadlocks when runs reuse the same files.
        files = {file_id: await self.require(file_id, lock=True) for file_id in sorted(file_ids)}
        for file_id in file_ids:
            file = files[file_id]
            parts.append(f"Attachment: {file.filename}\n{file.text_content}")
        context = "\n\n".join(parts)
        if len(context) > get_settings().run_context_max_chars:
            raise FileError("The combined run context exceeds the configured limit.", 413)
        return context
