








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





    
    group = GroupProfile(id="study-group", name="学习计划组", member_assistant_ids=["office"])
    config = runtime.groups.model_copy(deep=True)
    config.upsert(group)
    runtime.groups = runtime.config_store.save_groups(config)
    
    
    await runtime.group_event_repo.append(
        group.id, "t-search", "message", {"name": "office", "content": "预算先按三份来分吧"}
    )

    
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

    session = await runtime.sessions.create(title="回顾")
    session.memory.add_user("上周我们定了 A 方案")
    session.memory.add_assistant("对，A 方案先做起来。")
    await runtime.sessions.persist(session, include_messages=True)
    ctx = _make_ctx(runtime)

    
    only_me = await HistorySearchSkill().run(ctx, query="方案", author="我")
    assert only_me["results"], "应当能查到用户自己说过的那句"
    assert {item["author"] for item in only_me["results"]} == {"我"}

    
    future = await HistorySearchSkill().run(ctx, query="方案", since="2030-01-01")
    assert future["count"] == 0
    assert future["message"], "空结果要有可读说明，而不是一个空数组"

    
    
    assert day_range("", "2030-01-01")[1] is not None


@pytest.mark.asyncio
async def test_missing_source_is_reported_not_silent(runtime):

    runtime.config.settings.memory.long_term_enabled = False

    result = await HistorySearchSkill().run(_make_ctx(runtime), query="随便什么")

    assert result["notes"], "来源不可用必须在 notes 里如实说明"
    assert any("长期记忆" in item for item in result["notes"])
