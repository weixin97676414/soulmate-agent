






from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import uvicorn

from my_agent.config.paths import AppPaths
from my_agent.server.app import create_app
from my_agent.server.runtime import AppRuntime

from ..conftest import FakeLLM, tool_call  

TOKEN = "test-token"

TEST_CONFIRM_TIMEOUT = 5.0


@pytest.fixture
def runtime(tmp_path) -> AppRuntime:
    AppPaths(tmp_path / "data").ensure()
    rt = AppRuntime(AppPaths(tmp_path / "data"))
    
    
    
    
    
    
    rt.config.settings.security.confirm_mode = "interactive"
    rt.skills.guard.set_confirm_mode("interactive")  
    
    
    rt.config.settings.security.confirm_timeout_seconds = TEST_CONFIRM_TIMEOUT
    
    rt.path_policy = rt._build_path_policy()  
    return rt


@contextlib.asynccontextmanager
async def serve_runtime(runtime: AppRuntime, *, token: str = TOKEN) -> AsyncIterator[str]:






    app = create_app(runtime=runtime, token=token)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", access_log=False, timeout_keep_alive=5)
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))

    for _ in range(200):  
        if server.started:
            break
        await asyncio.sleep(0.01)
    assert server.started, "uvicorn 未能启动"

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=10)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
        sock.close()


@pytest.fixture
async def base_url(runtime):
    async with serve_runtime(runtime) as url:
        yield url


def make_client(base_url: str, token: str | None = TOKEN) -> httpx.AsyncClient:






    headers = {"X-Local-Token": token} if token else {}
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(30.0, read=30.0),
        trust_env=False,
    )


@pytest.fixture
async def client(base_url):
    async with make_client(base_url) as c:
        yield c


def install_fake_model(runtime: AppRuntime, llm) -> str:

    runtime.registry.register("fake", llm, is_default=True)
    return "fake"


async def read_sse(client: httpx.AsyncClient, payload: dict[str, Any]) -> list[tuple[str, dict]]:

    events: list[tuple[str, dict]] = []
    async with client.stream("POST", "/v1/chat", json=payload) as resp:
        assert resp.status_code == 200, await resp.aread()
        assert resp.headers["content-type"].startswith("text/event-stream")
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                events.append((current, json.loads(line[6:])))
                current = None
    return events


async def wait_for(predicate, *, timeout: float = 15.0) -> bool:





    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


@contextlib.asynccontextmanager
async def event_collector(
    client: httpx.AsyncClient,
) -> AsyncIterator[list[tuple[str, dict]]]:

    events: list[tuple[str, dict]] = []

    async def reader() -> None:
        try:
            async with client.stream("GET", "/v1/events") as response:
                if response.status_code != 200:
                    return
                current = None
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current = line[7:].strip()
                    elif line.startswith("data: ") and current:
                        events.append((current, json.loads(line[6:])))
                        current = None
        except (asyncio.CancelledError, httpx.HTTPError):
            pass

    task = asyncio.create_task(reader())
    try:
        
        assert await wait_for(lambda: any(e[0] == "ready" for e in events), timeout=5)
        yield events
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def read_sse_auto_approve(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> list[tuple[str, dict]]:






    events: list[tuple[str, dict]] = []
    async with client.stream("POST", "/v1/chat", json=payload) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[7:].strip()
            elif line.startswith("data: ") and current:
                data = json.loads(line[6:])
                events.append((current, data))
                if current == "permission_request":
                    await client.post(
                        "/v1/confirm",
                        json={"request_id": data["request_id"], "approved": True},
                    )
                current = None
    return events


def register_confirm_skill(runtime: AppRuntime, name: str = "write_file"):

    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name=name,
        display_name="写入文件",
        description="写入文件（测试用）",
        permission_level="confirm",
    )
    class _WriteSkill(BaseSkill):
        async def run(self, ctx, **params):
            return "写入成功"

    runtime.skills.register(_WriteSkill)
    return _WriteSkill


__all__ = [
    "FakeLLM",
    "TOKEN",
    "event_collector",
    "install_fake_model",
    "make_client",
    "read_sse",
    "read_sse_auto_approve",
    "register_confirm_skill",
    "serve_runtime",
    "tool_call",
    "wait_for",
]
