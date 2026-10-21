






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






    runtime = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await runtime.initialize()
    try:
        yield runtime.usage_repo
    finally:
        await runtime.shutdown()


async def test_cost_is_none_when_no_price_configured(repo):






    await repo.record(_record(cost=None))

    totals = await repo.totals()

    assert totals["cost"] is None
    assert totals["prompt_tokens"] == 10
    assert totals["completion_tokens"] == 5


async def test_cost_is_zero_when_explicitly_free(repo):

    await repo.record(_record(cost=0.0))

    totals = await repo.totals()

    assert totals["cost"] == 0.0
    assert totals["cost"] is not None


async def test_null_and_zero_can_coexist(repo):




    await repo.record(_record(cost=None))
    await repo.record(_record(cost=1.5))

    totals = await repo.totals()

    
    assert totals["cost"] == 1.5


async def test_by_model_and_by_day_keep_the_same_contract(repo):

    await repo.record(_record(cost=None))

    by_model = await repo.by_model()
    by_day = await repo.by_day(days=1)

    assert by_model
    assert by_day
    assert by_model[0]["cost"] is None
    assert by_day[0]["cost"] is None
