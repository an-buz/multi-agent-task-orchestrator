"""Probe real Docker isolation; generated Python never executes on the host."""

import asyncio
import json
from collections.abc import Generator
from uuid import uuid4

import docker
import pytest
from app.core.config import get_settings
from app.tools.runtime import ToolError, docker_code


@pytest.fixture(scope="module")
def executor_image() -> Generator[str]:
    client = docker.from_env()
    image = get_settings().code_executor_image

    try:
        try:
            client.images.get(image)
        except docker.errors.ImageNotFound:
            client.images.pull(image)

        yield image
    finally:
        client.close()


async def test_real_container_isolation_timeout_and_cleanup(
    executor_image: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_EXECUTOR_BACKEND", "docker")
    monkeypatch.setenv("CODE_EXECUTOR_IMAGE", executor_image)
    monkeypatch.setenv("TOOL_TIMEOUT", "10")

    identifier = uuid4()

    monkeypatch.setattr("app.tools.runtime.uuid4", lambda: identifier)
    get_settings.cache_clear()

    probe = """
import json, os, socket
from pathlib import Path
result = {"uid": os.getuid(), "cwd": os.getcwd()}
try:
    Path('/etc/orchestrator-probe').write_text('forbidden')
    result['root_readonly'] = False
except OSError:
    result['root_readonly'] = True
Path('/workspace/probe').write_text('allowed')
result['workspace'] = Path('/workspace/probe').read_text()
try:
    socket.create_connection(('1.1.1.1', 443), timeout=0.3)
    result['network_blocked'] = False
except OSError:
    result['network_blocked'] = True
result['memory'] = Path('/sys/fs/cgroup/memory.max').read_text().strip()
result['pids'] = Path('/sys/fs/cgroup/pids.max').read_text().strip()
result['cpu'] = Path('/sys/fs/cgroup/cpu.max').read_text().strip()
status = Path('/proc/self/status').read_text().splitlines()
result['caps'] = [line for line in status if line.startswith('CapEff:')][0]
keys = ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'TAVILY_API_KEY']
result['no_keys'] = all(key not in os.environ for key in keys)
print(json.dumps(result))
"""
    result = json.loads(await docker_code(probe))

    assert result["uid"] == 65534 and result["cwd"] == "/workspace"
    assert result["root_readonly"] and result["network_blocked"] and result["no_keys"]
    assert result["workspace"] == "allowed"
    assert result["memory"] == "134217728" and result["pids"] == "64"
    assert result["cpu"] == "50000 100000"
    assert result["caps"].split()[-1] == "0000000000000000"

    monkeypatch.setenv("TOOL_TIMEOUT", "2")
    get_settings.cache_clear()

    with pytest.raises(TimeoutError):
        await docker_code("while True: pass")

    monkeypatch.setenv("TOOL_OUTPUT_MAX_CHARS", "128")
    get_settings.cache_clear()

    with pytest.raises(ToolError, match="output"):
        await docker_code("print('x' * 10000)")

    client = docker.from_env()

    try:
        with pytest.raises(docker.errors.NotFound):
            await asyncio.to_thread(client.containers.get, f"orchestrator-{identifier.hex}")
    finally:
        client.close()


async def test_real_orphan_sweeper_only_removes_expired_owned_containers(
    executor_image: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.tools.containers import EXPIRES_LABEL, MANAGED_LABEL, SCOPE_LABEL, cleanup_containers

    scope = f"test-{uuid4().hex}"

    monkeypatch.setenv("CODE_EXECUTOR_BACKEND", "docker")
    monkeypatch.setenv("CODE_EXECUTOR_SCOPE", scope)
    monkeypatch.setenv("CODE_EXECUTOR_ORPHAN_AGE_SECONDS", "1")
    get_settings.cache_clear()

    now = datetime.now(UTC)

    labels = {MANAGED_LABEL: "code", SCOPE_LABEL: scope, EXPIRES_LABEL: str(now.timestamp() - 1)}

    client = docker.from_env()
    containers = []

    try:
        for metadata in [
            labels,
            {**labels, EXPIRES_LABEL: str(now.timestamp() + 3600)},
            {**labels, SCOPE_LABEL: f"other-{scope}"},
            {},
        ]:
            container = await asyncio.to_thread(
                client.containers.create,
                executor_image,
                command=["python", "-c", "import time; time.sleep(300)"],
                labels=metadata,
                network_disabled=True,
                read_only=True,
                user="65534:65534",
            )

            containers.append(container)

            await asyncio.to_thread(container.start)

        assert await cleanup_containers(datetime.now(UTC) + timedelta(seconds=2)) == 1

        with pytest.raises(docker.errors.NotFound):
            await asyncio.to_thread(containers[0].reload)

        for container in containers[1:]:
            await asyncio.to_thread(container.reload)

            assert container.status == "running"
    finally:
        for container in containers:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except docker.errors.NotFound:
                pass

        await asyncio.to_thread(client.close)
