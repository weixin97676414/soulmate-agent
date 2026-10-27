





from __future__ import annotations

import pytest

from my_agent.config.paths import AppPaths
from my_agent.server.runtime import AppRuntime


@pytest.fixture
def runtime(tmp_path):
    return AppRuntime(paths=AppPaths(tmp_path / "data").ensure())


async def _new_group(runtime, name: str) -> str:
    created = await runtime.orchestrator.create_group(
        name=name,
        member_ids=["soulmate", "LoveBuddy"],
        
        from_import=True,
    )
    return created["id"]


@pytest.mark.asyncio
async def test_distribute_context_writes_plan(runtime) -> None:
    group_id = await _new_group(runtime, "分配测试群")

    result = await runtime.orchestrator.distribute_context(
        group_id=group_id,
        thread_id="t1",
        items=[
            {"member_id": "soulmate", "brief": "你只负责登录页"},
            {"member_id": "LoveBuddy", "brief": "你只负责支付页"},
        ],
    )

    assert result["assigned"] == 2
    assert runtime._group_context_plan[(group_id, "t1", "soulmate")] == "你只负责登录页"
    assert runtime._group_context_plan[(group_id, "t1", "LoveBuddy")] == "你只负责支付页"


@pytest.mark.asyncio
async def test_distribute_context_rejects_member_not_in_group(runtime) -> None:
    group_id = await _new_group(runtime, "分配测试群2")

    with pytest.raises(ValueError):
        await runtime.orchestrator.distribute_context(
            group_id=group_id,
            thread_id="t1",
            items=[{"member_id": "RelationBuddy", "brief": "不在群里"}],
        )


@pytest.mark.asyncio
async def test_distribute_context_requires_thread_id(runtime) -> None:
    group_id = await _new_group(runtime, "分配测试群3")

    with pytest.raises(ValueError):
        await runtime.orchestrator.distribute_context(
            group_id=group_id, thread_id="  ", items=[{"member_id": "soulmate", "brief": "x"}]
        )
