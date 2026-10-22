

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from my_agent.llm.base import BaseLLM, LLMResponse, Message, StreamChunk, ToolCall, ToolSpec


class FakeLLM(BaseLLM):






    def __init__(self, script: list[Any], *, model_name: str = "fake-model") -> None:
        super().__init__(model_name=model_name, token_limit=8192)
        self._script = list(script)
        self.calls: list[list[Message]] = []
        
        
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

    async def stream(  
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        
        
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
















    from pathlib import Path

    from my_agent.skill import factory

    original = factory.resource_root
    factory.resource_root = lambda: Path("__no_factory_skills_in_tests__")  
    yield
    factory.resource_root = original  


@pytest.fixture
def tmp_paths(tmp_path):
    from my_agent.config.paths import AppPaths

    return AppPaths(tmp_path / "agent-data").ensure()


@pytest.fixture
async def skill_env(tmp_path):





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
