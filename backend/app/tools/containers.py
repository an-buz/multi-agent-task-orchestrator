"""Remove expired, explicitly owned code containers, never arbitrary Docker resources."""

import asyncio
import json
import math
from datetime import UTC, datetime

import structlog

from app.core.config import get_settings

MANAGED_LABEL = "orchestrator.managed"
SCOPE_LABEL = "orchestrator.scope"
EXPIRES_LABEL = "orchestrator.expires_at"
logger = structlog.get_logger()


async def docker_command(*arguments: str) -> str:
    settings = get_settings()
    process = await asyncio.create_subprocess_exec(
        "docker",
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        output = bytearray()
        async with asyncio.timeout(settings.cleanup_docker_timeout):
            while chunk := await process.stdout.read(4096):
                output.extend(chunk)
                if len(output) > settings.tool_output_max_chars:
                    raise ValueError("Docker response exceeds the output limit")
            if await process.wait() != 0:
                raise RuntimeError("Docker command failed")
        return output.decode("utf-8")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def cleanup_containers(now: datetime | None = None) -> int:
    settings = get_settings()
    if settings.code_executor_backend != "docker":
        return 0
    moment = now or datetime.now(UTC)
    removed = 0
    try:
        identifiers = (
            await docker_command(
                "ps",
                "--all",
                "--filter",
                f"label={MANAGED_LABEL}=code",
                "--filter",
                f"label={SCOPE_LABEL}={settings.code_executor_scope}",
                "--format",
                "{{.ID}}",
            )
        ).splitlines()
        for identifier in identifiers:
            if removed >= settings.cleanup_batch_size:
                break
            if not identifier or any(char not in "0123456789abcdef" for char in identifier):
                continue
            try:
                raw = await docker_command(
                    "inspect", "--format", "{{json .Config.Labels}}|{{.Created}}", identifier
                )
                labels_raw, created_raw = raw.strip().rsplit("|", 1)
                labels = json.loads(labels_raw)
                if (
                    labels.get(MANAGED_LABEL) != "code"
                    or labels.get(SCOPE_LABEL) != settings.code_executor_scope
                ):
                    continue
                expires = float(labels[EXPIRES_LABEL])
                if not math.isfinite(expires):
                    continue
                created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                if (
                    expires > moment.timestamp()
                    or (moment - created).total_seconds()
                    < settings.code_executor_orphan_age_seconds
                ):
                    continue
                await docker_command("rm", "--force", identifier)
                removed += 1
            except KeyError, ValueError, TypeError, AttributeError, RuntimeError, TimeoutError:
                # Unknown ownership or disappeared containers are never deletion authority.
                continue
    except Exception as exception:
        logger.warning("container_cleanup_deferred", error_type=type(exception).__name__)
    return removed
