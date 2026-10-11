"""pytest 公共夹具。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from my_agent.llm.base import BaseLLM, LLMResponse, Message, StreamChunk, ToolCall, ToolSpec


class FakeLLM(BaseLLM):
    """按预设剧本依次返回响应的假模型，用于验证 Agent 循环。

    ``script`` 每一项要么是 ``LLMResponse``（非流式），
    要么是 ``("text", "内容")`` / ``("tool", ToolCall)`` 的流式片段序列。
    """

    def __init__(self, script: list[Any], *, model_name: str = "fake-model") -> None:
        super().__init__(model_name=model_name, token_limit=8192)
        self._script = list(script)
        self.calls: list[list[Message]] = []
        # 每次调用时模型看到的工具列表。测试「工具是否随状态消失」时必须用它，
        # 光看 SkillManager 里的注册结果是不够的——那不代表模型真的能看到。
        self.tools_seen: list[list[ToolSpec]] = []

    def _next(self) -> Any:
        if not self._script:
            return LLMResponse(content="（剧本已耗尽）", finish_reason="stop")
        return self._script.pop(0)

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        # 采样参数。测试替身**必须**接受它们 —— FallbackLLM 会无条件转发，
        # 不接受就会 TypeError，而那看起来像是生产代码坏了
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        self.tools_seen.append(list(tools or []))
        item = self._next()
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(content=str(item), finish_reason="stop")

    async def stream(  # type: ignore[override]
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        # 采样参数。测试替身**必须**接受它们 —— FallbackLLM 会无条件转发，
        # 不接受就会 TypeError，而那看起来像是生产代码坏了
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append(list(messages))
        self.tools_seen.append(list(tools or []))
        item = self._next()

        if isinstance(item, LLMResponse):
            if item.content:
                for ch in item.content:
                    yield StreamChunk(delta=ch)
            yield StreamChunk(
                tool_calls=item.tool_calls or None,
                usage=item.usage or {"prompt_tokens": 10, "completion_tokens": 5},
                finish_reason=item.finish_reason or ("tool_calls" if item.tool_calls else "stop"),
            )
            return

        # 字符串：逐字流式返回
        for ch in str(item):
            yield StreamChunk(delta=ch)
        yield StreamChunk(
            usage={"prompt_tokens": 10, "completion_tokens": 5}, finish_reason="stop"
        )


def tool_call(
    name: str, arguments: dict[str, Any] | None = None, call_id: str = "call_1"
) -> ToolCall:
    import json

    args = arguments or {}
    return ToolCall(id=call_id, name=name, arguments=args, raw_arguments=json.dumps(args))


@pytest.fixture
def fake_llm_factory():
    return FakeLLM


@pytest.fixture(autouse=True, scope="session")
def _disable_factory_skills():
    """测试里**关掉出厂技能播种**（2026-10-07 加出厂技能时补的）。

    ⚠️ 为什么必须关：播种挂在 `AppRuntime.__init__` 里，而测试用的数据目录是全新的
    （没有 marker），于是**每个起 runtime 的用例都会真把 254 个技能装进临时目录** ——
    既慢，又会把涉及 `custom_skills` 的断言搅浑。
    实测就是这么红掉的：`test_buddy_transfer::test_apply_buddy_twice_is_idempotent`
    断言技能列表只有两个，结果多出 254 个。

    播种本身有专门用例覆盖（`tests/unit/test_factory_skills.py`，17 条），
    那里用假的资源根与假 runtime，不必依赖真实的 254 个技能。

    ⚠️ 实现方式是**把资源根指到一个不存在的目录**，而不是直接替掉
    `read_factory_index`：`test_factory_skills.py` 的 `resource` fixture 也要
    patch `resource_root`，而 function 级的 patch 会**覆盖**这里的 session 级 patch ——
    替掉函数的话两边就打架了（实测：那样 `TestSeed` 整组会因为它读的是真资源而红）。
    """
    from pathlib import Path

    from my_agent.skill import factory

    original = factory.resource_root
    factory.resource_root = lambda: Path("__no_factory_skills_in_tests__")  # type: ignore[assignment]
    yield
    factory.resource_root = original  # type: ignore[assignment]


@pytest.fixture
def tmp_paths(tmp_path):
    from my_agent.config.paths import AppPaths

    return AppPaths(tmp_path / "agent-data").ensure()


@pytest.fixture
async def skill_env(tmp_path):
    """一套完整的技能运行环境：路径 + 白名单 + 工作区 + 数据库仓储。

    办公/生活技能依赖面比较广（文件路径、产物目录、记账仓储…），
    手工拼装容易漏，统一在这里造好。
    """
    from types import SimpleNamespace

    from my_agent.config.paths import AppPaths
    from my_agent.security.paths import PathPolicy
    from my_agent.skill.base import SkillContext
    from my_agent.storage.db import Database
    from my_agent.storage.files import WorkspaceStore
    from my_agent.storage.life import ExpenseRepository, ReminderRepository

    paths = AppPaths(tmp_path / "AgentDesktop").ensure()
    database = Database(paths.db_file)
    await database.connect()

    workspace = WorkspaceStore(
        workspace_dir=paths.workspace_dir, artifacts_dir=paths.artifacts_dir, db=database
    )
    workspace.ensure_dirs()

    ctx = SkillContext(
        paths=paths,
        path_policy=PathPolicy(
            [str(tmp_path)], always_allowed=[paths.workspace_dir, paths.artifacts_dir]
        ),
        workspace=workspace,
        session_id="test-session",
        extra={
            "expenses": ExpenseRepository(database),
            "reminders": ReminderRepository(database),
        },
    )

    yield SimpleNamespace(
        ctx=ctx,
        paths=paths,
        workspace=workspace,
        db=database,
        root=tmp_path,
        expenses=ctx.extra["expenses"],
        reminders=ctx.extra["reminders"],
    )

    await database.close()
