"""用量费用聚合：必须区分「未配置价格」与「确实是 0 元」。

这两者在数据库里分别是 ``NULL`` 与 ``0.0``，界面也据此分别显示
「未配置价格」和「¥0.00」。聚合查询如果把 NULL 抹成 0，这个区分就没了 ——
**没配单价的用户会看到"今日费用 ¥0.00"，以为自己免费。**
"""

from __future__ import annotations

import time

import pytest

from my_agent.config.paths import AppPaths
from my_agent.llm.usage import Usage
from my_agent.server.runtime import AppRuntime
from my_agent.storage.usage import UsageRecord


def _record(**overrides) -> UsageRecord:
    payload = {
        "session_id": "s1",
        "model_id": "m1",
        "provider": "p",
        "usage": Usage(prompt_tokens=10, completion_tokens=5),
        "created_at": time.time(),
    }
    payload.update(overrides)
    return UsageRecord(**payload)


@pytest.fixture
async def repo(tmp_path):
    """自建一个已连接的 runtime。

    刻意**不**复用集成测试的 ``runtime`` fixture：那个只构造不连接数据库
    （多数用例通过 ``http`` 走应用，连接由应用负责），而这里要直接查仓库，
    必须显式 ``initialize()``。
    """
    runtime = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await runtime.initialize()
    try:
        yield runtime.usage_repo
    finally:
        await runtime.shutdown()


async def test_cost_is_none_when_no_price_configured(repo):
    """一条单价都没配 → 聚合费用必须是 ``None``。

    原实现写的是 ``SUM(COALESCE(cost, 0))``，于是它**永远是数字**，
    ``_shape`` 里那条 NULL 分支变成死代码 —— 而那段代码的注释恰恰写着
    "否则界面会把'未配置价格'显示成'¥0.00'，用户以为免费"。
    """
    await repo.record(_record(cost=None))

    totals = await repo.totals()

    assert totals["cost"] is None
    assert totals["prompt_tokens"] == 10
    assert totals["completion_tokens"] == 5


async def test_cost_is_zero_when_explicitly_free(repo):
    """真的 0 元要是数字 0，不能被一并当成"未配置"。"""
    await repo.record(_record(cost=0.0))

    totals = await repo.totals()

    assert totals["cost"] == 0.0
    assert totals["cost"] is not None


async def test_null_and_zero_can_coexist(repo):
    """**关键场景**：同一个模型上既有没配价的调用、又有配了价的调用。

    只要聚合里有一处 COALESCE，这种混合情况就会被悄悄抹平。
    """
    await repo.record(_record(cost=None))
    await repo.record(_record(cost=1.5))

    totals = await repo.totals()

    # NULL 被 SUM 忽略，剩下真实的那笔 —— 而不是 1.5 或 0
    assert totals["cost"] == 1.5


async def test_by_model_and_by_day_keep_the_same_contract(repo):
    """按模型 / 按日的分组聚合必须和总量用同一套语义。"""
    await repo.record(_record(cost=None))

    by_model = await repo.by_model()
    by_day = await repo.by_day(days=1)

    assert by_model
    assert by_day
    assert by_model[0]["cost"] is None
    assert by_day[0]["cost"] is None
