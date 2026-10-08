"""Tool permissions, native adapters, usage, budgets and PDF regression coverage."""

import asyncio
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.llm.provider import LLMResponse, ToolCall
from app.llm.providers import AnthropicProvider, MockLLMProvider, OpenAIProvider
from app.models.run_step import RunStep
from app.orchestrator.executor import DAGExecutor
from app.services.files import FileError, validate_text_file
from app.tools.runtime import ToolError, ToolRuntime, calculate, docker_code
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from test_executor import make_run
from test_runs import MemoryRunRepository


def call(name: str, **arguments: object) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "a + 1", "2 ** 10000", "1 / 0", "[1]", "True + 1", "1e200", "(-1)**0.5"],
)
def test_calculator_rejects_code_and_unbounded_arithmetic(expression: str) -> None:
    with pytest.raises((ToolError, SyntaxError, ZeroDivisionError, TypeError)):
        calculate(expression)


def test_calculator_arithmetic() -> None:
    assert calculate("-(2 + 3) * 4 + 10 / 2") == -15
    assert calculate("7 // 2 + 7 % 2 + 2 ** 3") == 12


async def test_tool_permissions_file_scope_and_strict_arguments() -> None:
    runtime = ToolRuntime(["calculator", "file_reader"], {"attached": "abcdef"})
    assert json.loads(await runtime.execute(call("calculator", expression="2+3"))) == {"value": 5}
    assert (
        json.loads(
            await runtime.execute(call("file_reader", file_id="attached", offset=2, limit=2))
        )["text"]
        == "cd"
    )
    for request in [
        call("file_reader", file_id="other"),
        call("file_reader", file_id="../../secret"),
        call("calculator", expression="1", permissions=["web_search"]),
        call("file_reader", file_id="attached", offset="0"),
        call("web_search", query="x"),
    ]:
        assert "error" in json.loads(await runtime.execute(request))


def pdf_bytes() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(40, 700, "Attachment fixture text")
    document.showPage()
    document.save()
    return output.getvalue()


def test_pdf_extraction_and_rejections(monkeypatch: pytest.MonkeyPatch) -> None:
    content = pdf_bytes()
    assert (
        "Attachment fixture text" in validate_text_file("brief.pdf", "application/pdf", content)[2]
    )
    writer = PdfWriter()
    writer.add_page(PdfReader(BytesIO(content)).pages[0])
    writer.encrypt("fixture-password")
    encrypted = BytesIO()
    writer.write(encrypted)
    blank_writer = PdfWriter()
    blank_writer.add_blank_page(width=300, height=300)
    blank = BytesIO()
    blank_writer.write(blank)
    for invalid in [b"fake", b"%PDF-1.7\nmalformed", encrypted.getvalue(), blank.getvalue()]:
        with pytest.raises(FileError):
            validate_text_file("brief.pdf", "application/pdf", invalid)
    monkeypatch.setenv("RUN_CONTEXT_MAX_CHARS", "4")
    get_settings.cache_clear()
    with pytest.raises(FileError):
        validate_text_file("brief.pdf", "application/pdf", content)


class FixtureTools(MockLLMProvider):
    def __init__(self, *, endless: bool = False, fail: bool = False) -> None:
        self.calls = 0
        self.endless = endless
        self.fail = fail
        self.responses = [
            LLMResponse.model_validate(item)
            for item in json.loads((Path(__file__).parent / "fixtures/llm/tools.json").read_text())
        ]
        self.closed = False

    async def complete_tools(
        self, system_prompt, messages, model, tools, *, temperature, max_tokens
    ):
        assert [tool["name"] for tool in tools] == ["calculator"]
        self.calls += 1
        if self.calls > 1:
            assert json.loads(messages[-1]["content"]) == {"value": 20.0}
            if self.fail:
                raise ValueError("private key")
        return self.responses[0 if self.endless else min(self.calls - 1, 1)]

    async def aclose(self) -> None:
        self.closed = True


def tool_step() -> RunStep:
    return RunStep(
        run_id=uuid4(),
        agent_id=uuid4(),
        step_number=1,
        input="Calculate",
        agent_config={
            "model": "claude-sonnet",
            "system_prompt": "Arithmetic",
            "temperature": 0.2,
            "max_tokens": 1024,
            "tools": ["calculator"],
        },
    )


async def test_tool_loop_preserves_all_usage_and_failure_usage() -> None:
    for fail in [False, True]:
        provider = FixtureTools(fail=fail)
        result = await DAGExecutor(None, lambda _, active=provider: active).complete(tool_step())
        assert provider.closed
        assert result.prompt_tokens == (10 if fail else 28)
        assert result.completion_tokens == (4 if fail else 10)
        if fail:
            assert result.response is None and result.error["code"] == "llm_error"
            assert "private" not in json.dumps(result.error)
        else:
            assert result.response.content == "The result is 20."


async def test_tool_loop_limit_and_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_MAX_ROUNDS", "1")
    get_settings.cache_clear()
    provider = FixtureTools(endless=True)
    result = await DAGExecutor(None, lambda _: provider).complete(tool_step())
    assert result.error["code"] == "tool_limit_exceeded"
    assert result.prompt_tokens == 20 and provider.calls == 2
    provider = FixtureTools()
    executor = DAGExecutor(None, lambda _: provider)
    result = await executor.complete(tool_step(), token_allowance=14)
    assert result.error["code"] == "token_budget_exceeded"
    assert result.prompt_tokens == 10 and provider.calls == 1
    result = await executor.complete(tool_step(), token_allowance=0)
    assert result.error["code"] == "token_budget_exceeded"
    assert provider.calls == 1


async def test_run_budget_counts_planning_and_serializes_independent_steps() -> None:
    repository, run = await make_run([[], []])
    run.planner_config = {**run.planner_config, "token_budget": run.total_tokens + 38}
    provider = FixtureTools()
    for step in repository.saved_steps:
        step.agent_config = tool_step().agent_config
    await DAGExecutor(repository, lambda _: provider).execute(run)
    assert run.status == "FAILED"
    assert repository.saved_steps[0].status == "COMPLETED"
    assert repository.saved_steps[1].error["code"] == "token_budget_exceeded"
    assert provider.calls == 2
    assert run.total_tokens == run.planning_prompt_tokens + run.planning_completion_tokens + 38


async def test_planner_budget_failure_preserves_reported_usage() -> None:
    from app.orchestrator.planner import PlannerExecutor
    from app.schemas.run import RunCreate
    from app.services.runs import RunService

    repository = MemoryRunRepository()
    created = await RunService(repository).create(
        RunCreate(
            workflow_id=repository.saved_workflow.id,
            task="Plan with a small budget",
            token_budget=1,
        )
    )
    run = repository.runs[created.id]
    await PlannerExecutor(repository).execute(run)
    assert run.status == "FAILED"
    assert run.planning_error["code"] == "token_budget_exceeded"
    assert run.total_tokens > 1
    assert run.total_tokens == run.planning_prompt_tokens + run.planning_completion_tokens


@pytest.mark.parametrize("budget", [0, -1, True, 1.5, "100"])
def test_token_budget_requires_positive_integer(budget: object) -> None:
    from app.schemas.run import RunCreate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunCreate(workflow_id=uuid4(), task="Plan", token_budget=budget)


async def test_web_search_mock_and_real_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    assert json.loads(
        await ToolRuntime(["web_search"]).execute(call("web_search", query="fixture"))
    )["mock"]
    monkeypatch.setenv("LLM_PROVIDER_MODE", "real")
    monkeypatch.setenv("TAVILY_API_KEY", "placeholder")
    get_settings.cache_clear()
    post = AsyncMock(
        return_value=SimpleNamespace(
            raise_for_status=Mock(),
            json=lambda: {
                "results": [
                    {
                        "title": "Source",
                        "url": "https://example.org",
                        "content": "Evidence",
                        "secret": "no",
                    }
                ]
            },
        )
    )
    client = AsyncMock()
    client.__aenter__.return_value.post = post
    monkeypatch.setattr("app.tools.runtime.httpx.AsyncClient", Mock(return_value=client))
    result = json.loads(
        await ToolRuntime(["web_search"]).execute(call("web_search", query="fixture"))
    )
    assert result["results"] == [
        {"title": "Source", "url": "https://example.org", "content": "Evidence"}
    ]
    assert post.call_args.kwargs["json"]["max_results"] == 5


async def test_docker_disabled_and_security_flags_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ToolError):
        await docker_code("print(1)")
    monkeypatch.setenv("CODE_EXECUTOR_BACKEND", "docker")
    get_settings.cache_clear()
    process = SimpleNamespace(
        stdout=SimpleNamespace(read=AsyncMock(side_effect=[b"42\n", b""])),
        wait=AsyncMock(return_value=0),
        returncode=0,
    )
    removal = SimpleNamespace(wait=AsyncMock(return_value=0))
    creation = SimpleNamespace(communicate=AsyncMock(return_value=(b"id", b"")), returncode=0)
    launch = AsyncMock(side_effect=[creation, process, removal])
    monkeypatch.setattr("app.tools.runtime.asyncio.create_subprocess_exec", launch)
    assert await docker_code("print(42)") == "42\n"
    args = launch.call_args_list[0].args
    for flag in [
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65534:65534",
        "--pull=never",
        "--memory=128m",
        "--pids-limit=64",
    ]:
        assert flag in args
    assert launch.call_args_list[1].args[:3] == ("docker", "start", "--attach")
    assert launch.call_args_list[2].args[:3] == ("docker", "rm", "--force")


async def test_docker_cancellation_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_EXECUTOR_BACKEND", "docker")
    get_settings.cache_clear()
    started = asyncio.Event()

    async def read(_: int) -> bytes:
        started.set()
        await asyncio.Event().wait()
        return b""

    process = SimpleNamespace(
        stdout=SimpleNamespace(read=read),
        wait=AsyncMock(return_value=0),
        returncode=None,
        kill=Mock(),
    )
    removal = SimpleNamespace(wait=AsyncMock(return_value=0))
    creation = SimpleNamespace(communicate=AsyncMock(return_value=(b"id", b"")), returncode=0)
    launch = AsyncMock(side_effect=[creation, process, removal])
    monkeypatch.setattr("app.tools.runtime.asyncio.create_subprocess_exec", launch)
    pending = asyncio.create_task(docker_code("while True: pass"))
    await started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert launch.call_args_list[2].args[:3] == ("docker", "rm", "--force")
    process.kill.assert_called_once()


async def test_native_openai_tool_wire_format(monkeypatch: pytest.MonkeyPatch) -> None:
    native_call = SimpleNamespace(
        type="function",
        id="c1",
        function=SimpleNamespace(name="calculator", arguments='{"expression":"2+3"}'),
        model_dump=lambda: {
            "type": "function",
            "id": "c1",
            "function": {"name": "calculator", "arguments": '{"expression":"2+3"}'},
        },
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[native_call]))
            ],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2),
        )
    )
    monkeypatch.setattr(
        "app.llm.providers.AsyncOpenAI",
        Mock(
            return_value=SimpleNamespace(
                chat=SimpleNamespace(completions=SimpleNamespace(create=create))
            )
        ),
    )
    response = await OpenAIProvider("placeholder").complete_tools(
        "system",
        [{"role": "user", "content": "query"}],
        "gpt-4o",
        ToolRuntime(["calculator"]).definitions(),
        temperature=0.2,
        max_tokens=100,
    )
    assert response.tool_calls[0].arguments == {"expression": "2+3"}
    assert (
        create.call_args.kwargs["tools"][0]["function"]["parameters"]["additionalProperties"]
        is False
    )
    assert response.message["tool_calls"][0]["id"] == "c1"


async def test_native_anthropic_groups_tool_results(monkeypatch: pytest.MonkeyPatch) -> None:
    block = SimpleNamespace(
        type="tool_use",
        id="c1",
        name="calculator",
        input={"expression": "2+3"},
        model_dump=lambda: {
            "type": "tool_use",
            "id": "c1",
            "name": "calculator",
            "input": {"expression": "2+3"},
        },
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[block], usage=SimpleNamespace(input_tokens=4, output_tokens=2)
        )
    )
    monkeypatch.setattr(
        "app.llm.providers.AsyncAnthropic",
        Mock(return_value=SimpleNamespace(messages=SimpleNamespace(create=create))),
    )
    messages = [
        {"role": "user", "content": "query"},
        {"role": "assistant", "blocks": [block.model_dump()]},
        {"role": "tool", "tool_call_id": "c1", "content": "5"},
        {"role": "tool", "tool_call_id": "c2", "content": "6"},
    ]
    response = await AnthropicProvider("placeholder").complete_tools(
        "system",
        messages,
        "claude-sonnet",
        ToolRuntime(["calculator"]).definitions(),
        temperature=0.2,
        max_tokens=100,
    )
    assert response.tool_calls[0].id == "c1"
    assert [
        block["tool_use_id"] for block in create.call_args.kwargs["messages"][-1]["content"]
    ] == ["c1", "c2"]
