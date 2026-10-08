"""Bounded tools with permissions supplied exclusively by the run snapshot."""

import ast
import asyncio
import json
import math
import operator
from typing import Any, cast
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.llm.provider import ToolCall


class ToolError(Exception):
    """Safe tool failure suitable for returning to a model."""


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Calculation(Arguments):
    expression: str = Field(min_length=1, max_length=500)


class FileRead(Arguments):
    file_id: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10000, ge=1, le=20000)


class Search(Arguments):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class Code(Arguments):
    code: str = Field(min_length=1, max_length=20000)


SCHEMAS: dict[str, tuple[type[Arguments], str]] = {
    "calculator": (Calculation, "Evaluate arithmetic: +, -, *, /, //, %, ** and parentheses."),
    "file_reader": (FileRead, "Read extracted text from a current run attachment by file_id."),
    "web_search": (Search, "Search the web and return source titles, URLs and excerpts."),
    "code_executor": (Code, "Execute Python in an isolated Docker container without networking."),
}


def calculate(expression: str) -> float:
    """Evaluate a small arithmetic AST, never Python code."""
    root = ast.parse(expression, mode="eval")
    if len(list(ast.walk(root))) > 100:
        raise ToolError("Expression is too complex.")
    binary = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            value = float(cast(int | float, node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolError("Exponent is too large.")
            value = binary[type(node.op)](left, right)
        else:
            raise ToolError("Only arithmetic expressions are supported.")
        if not isinstance(value, float | int) or not math.isfinite(value) or abs(value) > 1e100:
            raise ToolError("Result is outside the supported range.")
        return float(value)

    return visit(root.body)


async def docker_code(code: str) -> str:
    """Execute only inside Docker; cancellation and timeouts remove the container."""
    settings = get_settings()
    if settings.code_executor_backend != "docker":
        raise ToolError("Code executor is disabled.")
    name = f"orchestrator-{uuid4().hex}"
    process: asyncio.subprocess.Process | None = None

    async def provision() -> None:
        creation = await asyncio.create_subprocess_exec(
            "docker",
            "create",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            f"--memory={settings.code_executor_memory}",
            f"--memory-swap={settings.code_executor_memory}",
            f"--cpus={settings.code_executor_cpus}",
            f"--pids-limit={settings.code_executor_pids}",
            f"--tmpfs=/workspace:rw,noexec,nosuid,size={settings.code_executor_workspace_bytes},mode=1777",
            "--workdir=/workspace",
            "--log-driver=none",
            settings.code_executor_image,
            "python",
            "-I",
            "-B",
            "-c",
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            await asyncio.wait_for(creation.communicate(), timeout=settings.tool_timeout)
            if creation.returncode != 0:
                raise ToolError("Code container could not be created; check the configured image.")
        finally:
            if creation.returncode is None:
                creation.kill()
                await creation.wait()

    # Provisioning finishes before cleanup even when cancellation races Docker create.
    creation_task = asyncio.create_task(provision())
    try:
        await asyncio.shield(creation_task)
        process = await asyncio.create_subprocess_exec(
            "docker",
            "start",
            "--attach",
            name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        chunks = bytearray()
        async with asyncio.timeout(settings.tool_timeout):
            while chunk := await process.stdout.read(4096):
                chunks.extend(chunk)
                if len(chunks) > settings.tool_output_max_chars:
                    raise ToolError("Code output exceeds the configured limit.")
            if await process.wait() != 0:
                raise ToolError("Code execution failed.")
        return chunks.decode("utf-8", errors="replace")
    finally:

        async def cleanup() -> None:
            await asyncio.gather(creation_task, return_exceptions=True)
            removal = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "--force",
                name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(removal.wait(), timeout=10)
            except TimeoutError:
                removal.kill()
                await removal.wait()
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()

        await asyncio.shield(cleanup())


class ToolRuntime:
    def __init__(self, allowed: list[str], files: dict[str, str] | None = None) -> None:
        self.allowed = set(allowed)
        self.files = files or {}

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": SCHEMAS[name][1],
                "input_schema": SCHEMAS[name][0].model_json_schema(),
            }
            for name in sorted(self.allowed)
            if name in SCHEMAS
        ]

    async def execute(self, call: ToolCall) -> str:
        try:
            if call.name not in self.allowed or call.name not in SCHEMAS:
                raise ToolError("Tool is not permitted for this agent.")
            arguments = SCHEMAS[call.name][0].model_validate(call.arguments)
            if isinstance(arguments, Calculation):
                result: object = {"value": calculate(arguments.expression)}
            elif isinstance(arguments, FileRead):
                if arguments.file_id not in self.files:
                    raise ToolError("File is not attached to the current run.")
                text = self.files[arguments.file_id]
                result = {
                    "text": text[arguments.offset : arguments.offset + arguments.limit],
                    "total_chars": len(text),
                    "offset": arguments.offset,
                }
            elif isinstance(arguments, Search):
                settings = get_settings()
                if settings.llm_provider_mode == "mock":
                    result = {"results": [], "mock": True}
                else:
                    if not settings.tavily_api_key:
                        raise ToolError("Web search is not configured.")
                    async with httpx.AsyncClient(timeout=settings.tool_timeout) as client:
                        response = await client.post(
                            settings.tavily_search_url,
                            json={
                                "api_key": settings.tavily_api_key,
                                "query": arguments.query,
                                "max_results": arguments.max_results,
                                "include_raw_content": False,
                            },
                        )
                        response.raise_for_status()
                        result = {
                            "results": [
                                {
                                    key: str(item.get(key, ""))[:2000]
                                    for key in ("title", "url", "content")
                                }
                                for item in response.json().get("results", [])[
                                    : arguments.max_results
                                ]
                            ]
                        }
            else:
                assert isinstance(arguments, Code)
                result = {"stdout": await docker_code(arguments.code)}
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded) > get_settings().tool_output_max_chars:
                raise ToolError(
                    "Tool output exceeds the configured limit; request a smaller slice."
                )
            return encoded
        except ToolError as exception:
            return json.dumps({"error": str(exception)})
        except Exception:
            return json.dumps({"error": "Tool execution failed or arguments are invalid."})
