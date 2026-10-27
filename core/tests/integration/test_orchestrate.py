



















from __future__ import annotations

import asyncio
import json

import pytest

from my_agent.assistants import evolution
from my_agent.assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, read_file
from my_agent.errors import SkillExecutionError
from my_agent.llm.base import LLMResponse
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.orchestrate import (
    TeamAssignGroupRolesSkill,
    TeamClearGroupThreadSkill,
    TeamCreateAssistantSkill,
    TeamCreateGroupSkill,
    TeamCreateGroupThreadSkill,
    TeamDeleteGroupThreadSkill,
    TeamEnsureRequiredSkillsSkill,
    TeamListSkill,
    TeamRenameGroupThreadSkill,
    TeamStartDiscussionSkill,
    TeamUpdateAssistantSkill,
    TeamUpdateGroupSkill,
)
from tests.conftest import FakeLLM, tool_call

from .conftest import event_collector, install_fake_model, wait_for



_SETUP = {
    "identity": "负责把零散资料整理成结构化文档。",
    "abilities": "1. 读 Excel 与 Word；2. 按模板生成周报；3. 归档到产物目录。",
    "rules": "先确认范围再动手；不确定的字段先问，不要猜。",
    "tone": "像交付清单一样简洁，每条给依据，不寒暄。",
}


def _make_ctx(
    runtime,
    *,
    session_id: str = "s1",
    assistant_id: str = "RelationBuddy",
    mark_library: bool = True,
) -> SkillContext:








    if mark_library:
        runtime.buddy_library.checked = True
    return SkillContext(
        settings=runtime.config.settings,
        paths=runtime.paths,
        session_id=session_id,
        assistant_id=assistant_id,
        extra=runtime.skill_services_for(assistant_id),
    )


def _register_probe(runtime, calls: list[str], *, level: str = "admin") -> None:





    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="dangerous_op",
        display_name="清空数据",
        description="清空全部数据（测试用）",
        permission_level=level,
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  
            calls.append("dangerous_op")
            return "已清空"

    runtime.skills.register(_Probe)


async def _create_group(
    client, *, name: str = "研究组", member_ids: list[str] | None = None
) -> dict:
    created = await client.post(
        "/v1/groups",
        json={
            "name": name,
            "member_assistant_ids": member_ids or ["RelationBuddy", "LoveBuddy"],
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _confirmed_group(runtime, client, *, name: str = "研究组") -> dict:




    group = await _create_group(client, name=name)
    await TeamAssignGroupRolesSkill().run(
        _make_ctx(runtime),
        group_id=group["id"],
        reviewer_id="LoveBuddy",
        advisor_id="RelationBuddy",
    )
    return group





@pytest.mark.asyncio
async def test_list_gives_names_and_descriptions(runtime):

    result = await TeamListSkill().run(_make_ctx(runtime))

    assert result["count"] > 0, "内置搭子应当被列出来"
    for item in result["assistants"]:
        assert item["id"]
        assert item["name"]
        assert "description" in item
    assert isinstance(result["groups"], list)


@pytest.mark.asyncio
async def test_create_assistant_rejects_a_duplicate_name(runtime):

    existing = runtime.assistants.sorted()[0]

    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateAssistantSkill().run(
            _make_ctx(runtime), name=existing.name, description="重复的", **_SETUP
        )

    assert "已经有一个" in str(exc.value)
    assert existing.id in str(exc.value), "拒绝时要把现有那个的 id 告诉模型"


@pytest.mark.asyncio
async def test_create_assistant_reports_unknown_skills(runtime):

    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime),
        name="周报小助手",
        description="专门写周报",
        skills=["scheduled_task_list", "不存在的技能"],
        **_SETUP,
    )

    created = result["created"]
    assert created["name"] == "周报小助手"
    assert created["ignored_skills"] == ["不存在的技能"]
    profile = runtime.assistants.get(created["id"])
    assert profile is not None
    
    
    assert profile.enabled_skills == ["scheduled_task_list"]


@pytest.mark.asyncio
async def test_new_assistant_gets_a_full_setup(runtime):






    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime), name="资料整理师", description="整理资料成文档", **_SETUP
    )
    assistant_id = result["created"]["id"]

    identity = read_file(runtime.paths, assistant_id, IDENTITY_FILE)
    rules = read_file(runtime.paths, assistant_id, RULES_FILE)
    soul = read_file(runtime.paths, assistant_id, SOUL_FILE)

    assert _SETUP["identity"] in identity
    assert _SETUP["abilities"] in identity, "能力清单要落在 IDENTITY 里"
    assert _SETUP["rules"] in rules
    assert _SETUP["tone"] in soul
    
    assert "## 我能做什么" not in soul

    
    listing = await TeamListSkill().run(_make_ctx(runtime), assistant_id=assistant_id)
    assert len(listing["assistants"]) == 1
    entry = listing["assistants"][0]
    assert _SETUP["abilities"] in entry["identity"]
    assert _SETUP["rules"] in entry["rules"]
    assert _SETUP["tone"] in entry["tone"]


@pytest.mark.asyncio
async def test_assistant_setup_is_append_only(runtime):

    created = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime), name="资料整理师", description="整理资料成文档", **_SETUP
    )
    assistant_id = created["created"]["id"]
    before = read_file(runtime.paths, assistant_id, RULES_FILE)

    await TeamUpdateAssistantSkill().run(
        _make_ctx(runtime),
        assistant_id=assistant_id,
        rules_append="涉及删改文件时先列清单给我确认。",
        description_append="也支持批量归档。",
    )

    after = read_file(runtime.paths, assistant_id, RULES_FILE)
    assert before.strip() in after, "原有规则必须原样还在"
    assert "先列清单给我确认" in after
    profile = runtime.assistants.get(assistant_id)
    assert profile is not None
    assert profile.description.endswith("也支持批量归档。")


@pytest.mark.asyncio
async def test_config_changes_are_broadcast(runtime, client):




    async with event_collector(client) as events:
        await TeamCreateAssistantSkill().run(
            _make_ctx(runtime), name="资料整理师", description="整理资料成文档", **_SETUP
        )
        group = await TeamCreateGroupSkill().run(
            _make_ctx(runtime),
            name="资料组",
            member_ids=["RelationBuddy", "soulmate"],
            coordinator_id="RelationBuddy",
        )
        
        await TeamAssignGroupRolesSkill().run(
            _make_ctx(runtime),
            group_id=group["created"]["id"],
            reviewer_id="soulmate",
            advisor_id="LoveBuddy",
        )
        
        def _counts() -> tuple[int, int]:
            return (
                len([1 for name, _ in events if name == "assistants_changed"]),
                len([1 for name, _ in events if name == "groups_changed"]),
            )

        fired = await wait_for(lambda: _counts() >= (4, 2), timeout=10)

    assert fired, f"没有收到完整的配置变更事件：{[name for name, _ in events]}"
    
    
    
    assert _counts() == (4, 2)


@pytest.mark.asyncio
async def test_create_group_reports_unknown_members(runtime):

    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateGroupSkill().run(
            _make_ctx(runtime),
            name="两人组",
            member_ids=["RelationBuddy", "编造的id"],
            coordinator_id="RelationBuddy",
        )
    assert "至少要两个" in str(exc.value)
    assert "list_assistants" in str(exc.value), "拒绝时要告诉模型去哪儿拿真实 id"

    result = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="学习计划组",
        member_ids=["RelationBuddy", "LoveBuddy", "编造的id"],
        coordinator_id="RelationBuddy",
    )
    created = result["created"]
    assert created["ignored_members"] == ["编造的id"]
    member_ids = [item["id"] for item in created["members"]]
    
    assert {"RelationBuddy", "LoveBuddy"} <= set(member_ids)
    
    assert (runtime.assistants.get("BuddyManager").group_role or "") == "coordinator"
    assert not (runtime.assistants.get("RelationBuddy").group_role or "")
    assert not (runtime.assistants.get("LoveBuddy").group_role or ""), (
        "建群不该给没被指名的人安上角色"
    )
    
    assert created["existing_assistants"]
    
    assert "team_assign_group_roles" in created["next_step"]










@pytest.mark.asyncio
async def test_create_group_always_uses_buddy_manager_as_coordinator(runtime):




    result = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="自动总管的群",
        member_ids=["RelationBuddy", "LoveBuddy"],
    )
    created = result["created"]
    assert created["coordinator"]["id"] == "BuddyManager"
    assert runtime.groups.get(created["id"]).coordinator_id == "BuddyManager"
    assert (runtime.assistants.get("BuddyManager").group_role or "") == "coordinator"
    assert created["coordinator"]["name"] in result["message"]
    member_ids = [item["id"] for item in created["members"]]
    assert "BuddyManager" in member_ids, "Buddy Manager 必须自动进群"


@pytest.mark.asyncio
async def test_create_group_ignores_a_non_buddy_manager_coordinator(runtime):




    first = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="第一组",
        member_ids=["RelationBuddy", "LoveBuddy"],
    )
    await TeamAssignGroupRolesSkill().run(
        _make_ctx(runtime),
        group_id=first["created"]["id"],
        reviewer_id="LoveBuddy",
        advisor_id="soulmate",
    )
    assert (runtime.assistants.get("LoveBuddy").group_role or "") == "reviewer"

    second = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="第二组",
        member_ids=["LoveBuddy", "soulmate"],
        coordinator_id="LoveBuddy",
    )
    created = second["created"]
    assert created["coordinator"]["id"] == "BuddyManager", "总管恒为 Buddy Manager"
    assert (runtime.assistants.get("LoveBuddy").group_role or "") == "reviewer"


@pytest.mark.asyncio
async def test_remove_coordinator_clears_the_group_field(runtime):

    created = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="换人组",
        member_ids=["RelationBuddy", "LoveBuddy", "soulmate"],
    )
    group_id = created["created"]["id"]
    assert runtime.groups.get(group_id).coordinator_id == "BuddyManager"

    result = await TeamUpdateGroupSkill().run(
        _make_ctx(runtime),
        group_id=group_id,
        remove_member_ids=["BuddyManager"],
    )
    assert runtime.groups.get(group_id).coordinator_id == ""
    assert "总管" in result["message"]





@pytest.mark.asyncio
async def test_discussion_is_refused_until_roles_are_submitted(runtime, client):






    install_fake_model(runtime, FakeLLM(["不该跑到这里"]))
    group = await _create_group(client, name="没配角色的群")

    with pytest.raises(SkillExecutionError) as exc:
        await TeamStartDiscussionSkill().run(
            _make_ctx(runtime), topic="定一下这周的学习计划", group_id=group["id"]
        )

    message = str(exc.value)
    assert "team_assign_group_roles" in message, "拒绝时要告诉模型下一步该调哪个工具"
    assert "审核员" in message and "优化顾问" in message
    assert "没有「不需要」" in message, "不能留一句「不需要就算了」的口子"


@pytest.mark.asyncio
async def test_assign_roles_only_accepts_real_assistants(runtime, client):

    group = await _create_group(client, name="角色校验群")

    with pytest.raises(SkillExecutionError) as exc:
        await TeamAssignGroupRolesSkill().run(
            _make_ctx(runtime),
            group_id=group["id"],
            reviewer_id="编造的id",
            advisor_id="LoveBuddy",
        )
    assert "不存在" in str(exc.value)
    assert "team_list_assistants" in str(exc.value), "拒绝时要告诉模型去哪儿拿真 id"

    with pytest.raises(SkillExecutionError) as exc:
        await TeamAssignGroupRolesSkill().run(
            _make_ctx(runtime),
            group_id=group["id"],
            reviewer_id="LoveBuddy",
            advisor_id="LoveBuddy",
        )
    assert "同一个搭子" in str(exc.value)

    
    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert not stored.roles_ready()


@pytest.mark.asyncio
async def test_confirmed_roles_are_remembered_and_invalidated(runtime, client):





    group = await _create_group(
        client, name="角色记忆群", member_ids=["RelationBuddy", "LoveBuddy", "soulmate"]
    )

    async with event_collector(client) as events:
        confirmed = await TeamAssignGroupRolesSkill().run(
            _make_ctx(runtime),
            group_id=group["id"],
            reviewer_id="LoveBuddy",
            advisor_id="RelationBuddy",
        )
        fired = await wait_for(
            lambda: {"groups_changed", "assistants_changed"} <= {name for name, _ in events},
            timeout=10,
        )

    
    assert fired, f"配置改了就推事件，收到的是：{[name for name, _ in events]}"
    assert confirmed["confirmed"]["roles"]["reviewer"]["id"] == "LoveBuddy"
    assert confirmed["confirmed"]["roles"]["advisor"]["id"] == "RelationBuddy"

    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert stored.roles_ready()
    assert (stored.reviewer_id, stored.advisor_id) == ("LoveBuddy", "RelationBuddy")
    
    assert runtime.assistants.get("LoveBuddy").group_role == "reviewer"
    assert runtime.assistants.get("RelationBuddy").group_role == "advisor"

    
    updated = await TeamUpdateGroupSkill().run(
        _make_ctx(runtime), group_id=group["id"], remove_member_ids=["LoveBuddy"]
    )
    assert updated["group"]["roles_cleared"] == ["审核员"]
    assert "team_assign_group_roles" in updated["group"]["next_step"]
    
    assert "team_assign_group_roles" in updated["message"]

    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert not stored.roles_ready()

    install_fake_model(runtime, FakeLLM(["不该跑到这里"]))
    with pytest.raises(SkillExecutionError) as exc:
        await TeamStartDiscussionSkill().run(
            _make_ctx(runtime), topic="再来一次", group_id=group["id"]
        )
    
    assert "审核员" in str(exc.value)
    assert "team_assign_group_roles" in str(exc.value)





_DISCUSS_SCRIPT = [
    
    LLMResponse(
        content="",
        tool_calls=[tool_call("dangerous_op", {})],
        finish_reason="tool_calls",
    ),
    "已经清过了。\n[END_VOTE]",
    
    "同意结束。\n[AGREE]",
    
    "结论：数据已清空，建议下周再复核一次。",
]


@pytest.mark.asyncio
async def test_background_discussion_delivers_and_runs_admin_skill(runtime, client):

    calls: list[str] = []
    _register_probe(runtime, calls)
    install_fake_model(runtime, FakeLLM(list(_DISCUSS_SCRIPT)))
    session = (await client.post("/v1/sessions", json={"title": "发起讨论"})).json()
    
    group = await _confirmed_group(runtime, client)

    async with event_collector(client) as events:
        started = await TeamStartDiscussionSkill().run(
            _make_ctx(runtime, session_id=session["id"]),
            topic="定一下这周的学习计划，给出每天的任务",
            group_id=group["id"],
        )
        assert started["started"]["started"] is True

        finished = await wait_for(
            lambda: any(name == "group_task_done" for name, _ in events), timeout=30
        )
        assert finished, f"后台讨论没有结束，收到的事件：{[n for n, _ in events]}"

    
    assert calls == ["dangerous_op"]

    
    messages = (await client.get(f"/v1/sessions/{session['id']}/messages")).json()["messages"]
    assert messages, "结果必须落在会话里，否则重启后就找不到了"
    assert "结论" in messages[-1]["content"]

    
    kinds = [name for name, _ in events]
    assert "group_task_started" in kinds
    done = next(data for name, data in events if name == "group_task_done")
    assert done["outcome"] == "done"
    assert done["session_id"] == session["id"]
    assert done["group_id"] == group["id"]

    
    stored = (await client.get(f"/v1/groups/{group['id']}/messages")).json()["events"]
    assert any(item["event"] == "message" for item in stored)
    assert any(item["event"] == "summary" for item in stored)


@pytest.mark.asyncio
async def test_foreground_discussion_still_refuses_admin_skill(runtime, client):




    calls: list[str] = []
    _register_probe(runtime, calls)
    llm = FakeLLM(list(_DISCUSS_SCRIPT))
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="前台对照群")

    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", f"/v1/groups/{group['id']}/discuss", json={"topic": "清一下数据"}
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((current, json.loads(line[len("data: ") :])))

    assert calls == [], "前台的 admin 级技能不该被执行"
    assert "summary" in [name for name, _ in events], "被拒不等于整场讨论崩掉"

    
    
    tool_messages = [
        message for call in llm.calls for message in call if message.role == "tool"
    ]
    assert any(
        "未开启" in (message.content or "") for message in tool_messages
    ), "拒绝的原因必须作为工具结果回到模型手里"





@pytest.mark.asyncio
async def test_custom_assistant_cannot_become_coordinator(runtime):

    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateAssistantSkill().run(
            _make_ctx(runtime),
            name="小红书策划师",
            description="负责选题策划",
            group_role="coordinator",
            skills=["kb_search"],
            **_SETUP,
        )
    assert "Buddy Manager" in str(exc.value)


@pytest.mark.asyncio
async def test_advisor_gets_thinking_rule_only(runtime):

    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime),
        name="内容优化顾问",
        description="交付后给优化建议",
        group_role="advisor",
        **_SETUP,
    )
    created = result["created"]
    rules = read_file(runtime.paths, created["id"], RULES_FILE)
    assert "ai_thinking_mode" in rules
    assert "team_restructure" not in rules


@pytest.mark.asyncio
async def test_plain_assistant_gets_only_the_evolution_rule(runtime):






    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime), name="周报助手", description="写周报", **_SETUP
    )
    created = result["created"]
    rules = read_file(runtime.paths, created["id"], RULES_FILE)
    
    assert "ai_thinking_mode" not in rules
    assert "team_restructure" not in rules
    
    assert evolution.SECTION_TITLE in rules
    assert evolution.task_name("周报助手") in rules
    imposed = created["imposed_rules"]
    assert len(imposed) == 1
    assert evolution.SECTION_TITLE in imposed[0]


@pytest.mark.asyncio
async def test_ensure_required_skills_backfills(runtime):




    from my_agent.assistants.persona import write_file

    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime),
        name="策划师二号",
        description="负责策划",
        group_role="advisor",
        skills=["kb_search"],
        **_SETUP,
    )
    assistant_id = result["created"]["id"]
    
    profile = runtime.assistants.get(assistant_id)
    config = runtime.assistants.model_copy(deep=True)
    config.upsert(profile.model_copy(update={"enabled_skills": ["kb_search"]}))
    runtime.save_assistants(config)
    write_file(runtime.paths, assistant_id, RULES_FILE, "没有条款的规则。")

    fixed = await TeamEnsureRequiredSkillsSkill().run(
        _make_ctx(runtime), assistant_ids=[assistant_id]
    )
    item = fixed["result"]["assistants"][0]
    assert item["id"] == assistant_id
    assert set(item["added_skills"]) >= {"self_growth", "ai_thinking_mode"}
    assert "team_restructure" not in item["added_skills"]
    assert any("ai_thinking_mode" in r for r in item["imposed_rules"])
    assert not any("team_restructure" in r for r in item["imposed_rules"])

    profile2 = runtime.assistants.get(assistant_id)
    assert profile2 is not None
    assert set(profile2.enabled_skills) >= {"kb_search", "self_growth", "ai_thinking_mode"}
    assert "team_restructure" not in profile2.enabled_skills
    rules = read_file(runtime.paths, assistant_id, RULES_FILE)
    assert "ai_thinking_mode" in rules
    assert "team_restructure" not in rules





@pytest.mark.asyncio
async def test_stop_discussion_cancels_task(runtime):

    async def _slow() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(_slow())
    runtime.orchestrator._tasks["grp-test"] = task  

    result = await runtime.orchestrator.stop_discussion("grp-test")
    assert result["stopped"] is True
    with pytest.raises(asyncio.CancelledError):
        await task

    again = await runtime.orchestrator.stop_discussion("grp-test")
    assert again["stopped"] is False


@pytest.mark.asyncio
async def test_stop_route_reports_not_running(runtime, client):

    group = await _create_group(client, name="停一个没在跑的群")
    resp = await client.post(f"/v1/groups/{group['id']}/stop")
    assert resp.status_code == 200
    assert resp.json() == {"group_id": group["id"], "stopped": False}

    missing = await client.post("/v1/groups/不存在的群/stop")
    assert missing.status_code == 404





@pytest.mark.asyncio
async def test_create_needs_library_check_first(runtime):






    runtime.buddy_library.checked = False
    ctx = _make_ctx(runtime, mark_library=False)

    with pytest.raises(SkillExecutionError) as assistant_exc:
        await TeamCreateAssistantSkill().run(ctx, name="新搭子", description="x", **_SETUP)
    assert "buddy_library_list" in str(assistant_exc.value)

    with pytest.raises(SkillExecutionError) as group_exc:
        await TeamCreateGroupSkill().run(
            ctx,
            name="新群",
            member_ids=["RelationBuddy", "LoveBuddy"],
            coordinator_id="RelationBuddy",
        )
    assert "buddy_library_list" in str(group_exc.value)


@pytest.mark.asyncio
async def test_import_bypasses_library_gate(runtime):




    runtime.buddy_library.checked = False

    created = await runtime.orchestrator.create_assistant(
        name="导入来的搭子", description="从包里来的", from_import=True
    )

    assert runtime.assistants.get(created["id"]) is not None





async def _make_group(runtime, name: str = "对话管理测试群") -> str:
    created = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name=name,
        member_ids=["RelationBuddy", "LoveBuddy"],
        coordinator_id="RelationBuddy",
    )
    return created["created"]["id"]


@pytest.mark.asyncio
async def test_列表里带上每个群的对话(runtime, client):









    group_id = await _make_group(runtime)
    created = await TeamCreateGroupThreadSkill().run(
        _make_ctx(runtime), group_id=group_id, title="预算复盘"
    )

    listed = await TeamListSkill().run(_make_ctx(runtime))

    group = next(item for item in listed["groups"] if item["id"] == group_id)
    assert [item["id"] for item in group["threads"]] == [created["thread"]["id"]]
    assert group["threads"][0]["title"] == "预算复盘"


@pytest.mark.asyncio
async def test_AI_可以建改名清空删群对话(runtime, client):





    group_id = await _make_group(runtime)
    ctx = _make_ctx(runtime)

    created = await TeamCreateGroupThreadSkill().run(ctx, group_id=group_id, title="预算复盘")
    thread_id = created["thread"]["id"]
    assert created["thread"]["title"] == "预算复盘"
    
    await TeamCreateGroupThreadSkill().run(ctx, group_id=group_id, title="另一条留着")

    
    await runtime.group_event_repo.append(group_id, thread_id, "topic", {"content": "聊预算"})
    assert len(await runtime.group_event_repo.list_events(group_id, thread_id)) == 1

    
    renamed = await TeamRenameGroupThreadSkill().run(
        ctx, group_id=group_id, thread_id=thread_id, title="预算复盘（第二轮）"
    )
    assert renamed["after"] == "预算复盘（第二轮）"

    
    cleared = await TeamClearGroupThreadSkill().run(ctx, group_id=group_id, thread_id=thread_id)
    assert cleared["removed"] == 1
    assert await runtime.group_event_repo.list_events(group_id, thread_id) == []
    assert await runtime.group_thread_repo.get(group_id, thread_id) is not None

    
    deleted = await TeamDeleteGroupThreadSkill().run(ctx, group_id=group_id, thread_id=thread_id)
    assert deleted["deleted_title"] == "预算复盘（第二轮）"
    assert await runtime.group_thread_repo.get(group_id, thread_id) is None
    assert deleted["remaining"] == 1, "另一条应当还在"


@pytest.mark.asyncio
async def test_最后一条群对话删不掉(runtime, client):





    group_id = await _make_group(runtime)
    created = await TeamCreateGroupThreadSkill().run(
        _make_ctx(runtime), group_id=group_id, title="唯一的一条"
    )

    with pytest.raises(SkillExecutionError) as exc:
        await TeamDeleteGroupThreadSkill().run(
            _make_ctx(runtime), group_id=group_id, thread_id=created["thread"]["id"]
        )

    assert "不能删" in str(exc.value)
    assert await runtime.group_thread_repo.get(group_id, created["thread"]["id"]) is not None, (
        "被拒绝之后那条对话必须原样还在"
    )


@pytest.mark.asyncio
async def test_动不了别的群的对话(runtime, client):






    group_a = await _make_group(runtime, name="甲群")
    group_b = await _make_group(runtime, name="乙群")
    
    made = await TeamCreateGroupThreadSkill().run(
        _make_ctx(runtime), group_id=group_b, title="乙群的对话"
    )
    thread_b = made["thread"]

    with pytest.raises(SkillExecutionError):
        await TeamRenameGroupThreadSkill().run(
            _make_ctx(runtime), group_id=group_a, thread_id=thread_b["id"], title="改错了"
        )

    
    assert (await runtime.group_thread_repo.get(group_b, thread_b["id"]))["title"] == "乙群的对话"


@pytest.mark.asyncio
async def test_群对话变动会广播(runtime, client):






    group_id = await _make_group(runtime)

    async with event_collector(client) as events:
        await TeamCreateGroupThreadSkill().run(
            _make_ctx(runtime), group_id=group_id, title="新的一条"
        )
        assert await wait_for(
            lambda: any(name == "group_threads_changed" for name, _ in events), timeout=5
        )

    payload = next(payload for name, payload in events if name == "group_threads_changed")
    assert payload["group_id"] == group_id
