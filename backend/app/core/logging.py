"""Structured logging setup."""

import logging
import os
import sys
from typing import Literal

import structlog


def configure_logging(
    log_level: str,
    *,
    log_format: Literal["auto", "console", "json"] = "json",
    log_colors: Literal["auto", "always", "never"] = "auto",
) -> None:
    """Configure standard logging and structlog processors."""

    console = log_format == "console" or (log_format == "auto" and sys.stderr.isatty())
    colors = log_colors == "always" or (
        log_colors == "auto" and sys.stderr.isatty() and "NO_COLOR" not in os.environ
    )

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer(colors=colors, force_colors=log_colors == "always")
        if console
        else structlog.processors.JSONRenderer()
    )

    handler = logging.StreamHandler(sys.stderr)

    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                *([] if console else [structlog.processors.format_exc_info]),
                renderer,
            ],
        )
    )
    logging.basicConfig(level=log_level.upper(), handlers=[handler], force=True)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
