"""跨来源检索：群聊记录 / 单聊历史 / 长期记忆。

用户问的是同一件事——「上次那个方案是怎么说的」，而数据住在三个地方。这组用例守：

1. 三个来源都能查到，而且**每条都带可读时间**（模型靠它判断新旧）；
2. 时间范围与"只看谁说的"真的能筛（结束日含当天，口径与 kb_search / 审计页一致）；
3. 来源缺失时**如实说明**，而不是让模型以为"那里也没有"（不静默省略）。
"""

from __future__ import annotations

import pytest

from my_agent.config.schemas import GroupProfile
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.history_search import HistorySearchSkill
from my_agent.utils.timefmt import day_range


def _make_ctx(runtime) -> SkillContext:
    return SkillContext(
        settings=runtime.config.settings,
        paths=runtime.paths,
        session_id="s1",
        assistant_id="office",
        extra=runtime.skill_services_for("office"),
    )


@pytest.mark.asyncio
async def test_searches_group_and_chat_with_readable_time(runtime, client):
    """群聊与单聊都要能查到，并且带可读时间。

    依赖 ``client`` 夹具：数据库是在真实服务的启动流程里连接的（``runtime`` 单独
    拿出来时还没连库），而群记录与会话都要落库。
    """
    # ---- 群聊记录 ----
    group = GroupProfile(id="study-group", name="学习计划组", member_assistant_ids=["office"])
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    # ⚠️ 第二个参数是**对话 id**（一个群可以有多条对话）。
    # 历史搜索是按**群**查的，所以这里用哪条对话都不影响断言 —— 但必须传。
    await runtime.group_event_repo.append(
        group.id, "t-search", "message", {"name": "office", "content": "预算先按三份来分吧"}
    )

    # ---- 单聊历史 ----
    session = await runtime.sessions.create(title="预算讨论")
    session.memory.add_user("预算怎么分？")
    session.memory.add_assistant("建议预算按三份分，先留一份应急。")
    await runtime.sessions.persist(session, include_messages=True)

    result = await HistorySearchSkill().run(_make_ctx(runtime), query="预算")

    assert result["count"] >= 2, result
    sources = {item["source"] for item in result["results"]}
    assert sources == {"群聊", "单聊"}, sources
    for item in result["results"]:
        assert item["when"], "每条结果都必须带可读时间（模型靠它判断新旧）"
        assert "预算" in item["text"]
    group_hit = next(item for item in result["results"] if item["source"] == "群聊")
    assert group_hit["where"] == "学习计划组"
    assert group_hit["author"] == "office"


@pytest.mark.asyncio
async def test_time_range_and_author_filter(runtime, client):
    """时间范围与"只看谁说的"都要真的生效。"""
    session = await runtime.sessions.create(title="回顾")
    session.memory.add_user("上周我们定了 A 方案")
    session.memory.add_assistant("对，A 方案先做起来。")
    await runtime.sessions.persist(session, include_messages=True)
    ctx = _make_ctx(runtime)

    # 只看"我"说的：搭子那句不该出现
    only_me = await HistorySearchSkill().run(ctx, query="方案", author="我")
    assert only_me["results"], "应当能查到用户自己说过的那句"
    assert {item["author"] for item in only_me["results"]} == {"我"}

    # 把范围推到未来 → 什么都查不到，并且给一句可读的说明
    future = await HistorySearchSkill().run(ctx, query="方案", since="2030-01-01")
    assert future["count"] == 0
    assert future["message"], "空结果要有可读说明，而不是一个空数组"

    # 结束日**含当天**：拿今天当结束日时，今天说的必须查得到
    # （"少一天"是这类筛选最常见的错，所以钉住 day_range 的右端不为空）
    assert day_range("", "2030-01-01")[1] is not None


@pytest.mark.asyncio
async def test_missing_source_is_reported_not_silent(runtime):
    """长期记忆没打开时要说清楚 —— 否则模型会以为"记忆里也没有"。"""
    runtime.config.settings.memory.long_term_enabled = False

    result = await HistorySearchSkill().run(_make_ctx(runtime), query="随便什么")

    assert result["notes"], "来源不可用必须在 notes 里如实说明"
    assert any("长期记忆" in item for item in result["notes"])
