"""Domain error base classes."""


class AppError(Exception):
    """Base for expected application errors."""

    code = "application_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
