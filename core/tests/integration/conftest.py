"""集成测试公共夹具：一套跑在真实 uvicorn 上的 HTTP 客户端。

**为什么必须起真实服务而不是 httpx.ASGITransport**：
ASGITransport 会把整个响应体缓冲完再交给调用方，于是 SSE 流永远读不到内容，
「边读流边发别的请求」这类流程必然死锁到超时。真实监听端口才能验证流式与并发。
"""

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

from ..conftest import FakeLLM, tool_call  # noqa: F401 - 供各测试模块再导出使用

TOKEN = "test-token"
# 测试里把确认超时压到 5 秒，避免用例失败时白等 2 分钟
TEST_CONFIRM_TIMEOUT = 5.0


@pytest.fixture
def runtime(tmp_path) -> AppRuntime:
    AppPaths(tmp_path / "data").ensure()
    rt = AppRuntime(AppPaths(tmp_path / "data"))
    # 这一套夹具默认跑「每次确认」模式，**必须显式钉住**，不能跟着出厂默认走：
    # 集成用例里有一大批是专门验确认链路的（弹窗 / 批准 / 拒绝 / 审计），它们要的是
    # "确认框真的弹出来"。而默认值是会变的（近期翻过一次：自动批准 → 每次确认），
    # 一旦它恰好不是这一档，这些用例就会静默地什么都不验直接变绿。
    # 想验自动批准 / 放开高危级的用例，请在自己的 SkillContext 上显式指定
    # （见 test_tasks_routes.py 里那条定时任务用例）。
    rt.config.settings.security.confirm_mode = "interactive"
    rt.skills.guard.set_confirm_mode("interactive")  # 守卫是按 settings 建出来的
    # ⚠️ 这一行已经**没有效果**（确认改为永不超时），但保留着不会有害：
    # 字段还在（为兼容老配置），只是不再被读。见 schemas.SecuritySettings 的说明。
    rt.config.settings.security.confirm_timeout_seconds = TEST_CONFIRM_TIMEOUT
    # 默认放开白名单，个别用例会自行收紧
    rt.path_policy = rt._build_path_policy()  # noqa: SLF001
    return rt


@contextlib.asynccontextmanager
async def serve_runtime(runtime: AppRuntime, *, token: str = TOKEN) -> AsyncIterator[str]:
    """在随机空闲端口上跑一个真实 uvicorn，产出它的 base_url。

    抽成公共工具是因为：需要"自定义 runtime + 真实 HTTP"的用例越来越多
    （密钥托管、泄露扫描…），各自复制一份启动/收尾逻辑很容易漏掉清理，
    留下一堆占着端口的僵尸协程。
    """
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

    for _ in range(200):  # 最多等 2 秒
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
    """构造指向本地服务的客户端。

    ``trust_env=False`` 是必需的：Windows 上 httpx 会通过
    ``urllib.request.getproxies()`` 读取**注册表**里的系统代理设置，
    一旦用户配了代理，对 127.0.0.1 的请求也会被转发出去而拿到 502。
    """
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
    """把假模型注册进运行时，返回模型 id。"""
    runtime.registry.register("fake", llm, is_default=True)
    return "fake"


async def read_sse(client: httpx.AsyncClient, payload: dict[str, Any]) -> list[tuple[str, dict]]:
    """消费一次对话的完整 SSE 流，返回 [(event, data), ...]。"""
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
    """轮询等待条件成立。

    事件推送是长连接，直接 ``async for`` 会在没有事件时永久挂住，
    必须用「后台收集 + 主线程轮询条件」的方式，这个函数是后半段。
    """
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
    """订阅 ``/v1/events`` 并把收到的事件累积到列表里。"""
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
        # 等首帧 ready，确保订阅已经建立，否则后面的触发会丢事件
        assert await wait_for(lambda: any(e[0] == "ready" for e in events), timeout=5)
        yield events
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def read_sse_auto_approve(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> list[tuple[str, dict]]:
    """消费一次对话的 SSE 流，并**自动批准**所有权限确认请求。

    用于那些「真正要验证的是工具执行结果」的用例：不关心确认交互，
    但流程里又确实会碰到 confirm 级工具，不批就会一直等到超时。
    需要验证确认交互本身的用例请用 read_sse + 手动回传。
    """
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
    """注册一个 confirm 级技能，用于测试权限确认流程。"""
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
