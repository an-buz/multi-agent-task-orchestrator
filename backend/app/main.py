"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)

app = FastAPI(title="Multi-Agent Task Orchestrator API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    _request: Request, exception: RequestValidationError
) -> JSONResponse:
    # Do not echo raw prompts or malformed Unicode back through the JSON encoder.
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exception.errors(), exclude={"input", "ctx"})},
    )


@app.exception_handler(AppError)
async def handle_domain_error(_request: Request, exception: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=getattr(exception, "status_code", 409),
        content={
            "error": {
                "code": exception.code,
                "message": exception.message,
                "details": exception.details,
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, _exception: Exception) -> JSONResponse:
    """Return the common API error envelope for unexpected failures."""
    # Exception messages/tracebacks can expose provider keys or uploaded content.
    logger.error("request_failed", method=_request.method, error_type=type(_exception).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {},
            }
        },
    )


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return process liveness status."""
    return {"status": "ok"}
