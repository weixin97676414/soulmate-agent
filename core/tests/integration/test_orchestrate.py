"""搭子团队：AI 自己组队，并把群讨论挪到后台跑。

用户的原话是「让 AI 自己建搭子、自己建群」，外加一条很具体的规则：

> 需要在确认之前拉取现有搭子的名称列表与简介列表，如果有功能相同的则使用现有的，
> 没有合适的需要补充的时候才进行创建

这组用例守五件事：

1. 「先查再建」是**硬约束**：只写在工具描述里是没用的，模型照样会建重复的，
   所以同名必须直接被拒；``team_list_assistants`` 得真的给出名称与简介；
2. 建群要**如实报出**不存在的成员，而不是静默丢掉（不静默省略）；
2.5 群角色（审核员 / 优化顾问）**绕不过去**：建群后必须调
   ``team_assign_group_roles`` 交出真搭子 id，否则开讨论直接被拒；系统不再兜底补人，
   提交的角色被移出群后确认也要作废；
3. 后台讨论跑完，结论**写回发起它的那条会话**，并推 started / done 两条事件；
4. 后台讨论里 admin（高危）级技能**真的能执行**（无人值守、没有确认通道），
   而**前台**的群讨论依然拒绝它 —— 有人能点确认的地方就不该静默执行高危操作。
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from my_agent.assistants import evolution
from my_agent.assistants.persona import IDENTITY_FILE, RULES_FILE, SOUL_FILE, read_file
from my_agent.errors import SkillExecutionError
from my_agent.llm.base import LLMResponse
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.orchestrate import (
    GroupCreateParams,
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

# 新建搭子时要写全的四块设定（技能把它们做成了必填参数）。
# 用同一份常量喂所有用例，改动时只改一处。
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
    """技能运行环境：extra 里放的就是 runtime 注入给技能的那份服务。

    ⚠️ 顺手把"官网搭子库**已经查过**"置位：2026-09-28 起，"新建搭子 / 建群之前
    必须先查官网搭子库"是一条硬闸门（见 `orchestrator._ensure_library_checked`），
    而这一整个文件考的是"建搭子 / 建群"本身。**闸门自己有专门的用例**
    （见文件末尾 `test_create_needs_library_check_first`），所以这里放行不会把
    那条约束考没了。
    """
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
    """注册一个高危（默认 admin）级探针技能。

    拿**执行痕迹**断言，而不是拿模型的措辞：要证明的是"这个技能真的被跑了"，
    措辞每次都可能不一样，用它当断言等于埋一个偶尔才红的用例。
    """
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="dangerous_op",
        display_name="清空数据",
        description="清空全部数据（测试用）",
        permission_level=level,
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
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
    """建群 **并提交两个群角色** —— 现在，少了这一步开不了讨论。

    顺序刻意按约定来：优化顾问在前（RelationBuddy 先发言）、审核员在最后（LoveBuddy）。
    """
    group = await _create_group(client, name=name)
    await TeamAssignGroupRolesSkill().run(
        _make_ctx(runtime),
        group_id=group["id"],
        reviewer_id="LoveBuddy",
        advisor_id="RelationBuddy",
    )
    return group


# --------------------------------------------------------------------------- #
# 一、「先查再建」
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_gives_names_and_descriptions(runtime):
    """清单里必须有**名称与简介** —— 只有 id 的话，模型判断不出能不能复用。"""
    result = await TeamListSkill().run(_make_ctx(runtime))

    assert result["count"] > 0, "内置搭子应当被列出来"
    for item in result["assistants"]:
        assert item["id"]
        assert item["name"]
        assert "description" in item
    assert isinstance(result["groups"], list)


@pytest.mark.asyncio
async def test_create_assistant_rejects_a_duplicate_name(runtime):
    """同名直接拒绝：这是"能复用就复用"唯一能真正生效的地方。"""
    existing = runtime.assistants.sorted()[0]

    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateAssistantSkill().run(
            _make_ctx(runtime), name=existing.name, description="重复的", **_SETUP
        )

    assert "已经有一个" in str(exc.value)
    assert existing.id in str(exc.value), "拒绝时要把现有那个的 id 告诉模型"


@pytest.mark.asyncio
async def test_create_assistant_reports_unknown_skills(runtime):
    """技能名写错时**不能装作装上了** —— 否则模型会一直依赖一个不会生效的能力。"""
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
    # ⚠️ 起**不再补必装技能**：`self_growth` / `ai_thinking_mode` 都划进
    # 「内置技能」，每个搭子恒有（见 skill/groups.py）—— 白名单里只留用户/AI 勾的那几个。
    assert profile.enabled_skills == ["scheduled_task_list"]


@pytest.mark.asyncio
async def test_new_assistant_gets_a_full_setup(runtime):
    """新建搭子必须写全**身份 / 能力 / 规则 / 语气**四块。

    用户的原话：「AI 创建的搭子是要处理一定任务的，所以必须有完整的身份，功能，
    以及规则……soul 里应该是根据这个搭子的功能和任务给予具体的语气风格」。
    原先只写一句 `你是 X`，那不算设定。
    """
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
    # 语气文件不该混进身份话术（那是 IDENTITY 的活，混在一起以后就分不开了）
    assert "## 我能做什么" not in soul

    # 清单里能拿到这三份全文：别的搭子据此判断"它能不能担这件事"
    listing = await TeamListSkill().run(_make_ctx(runtime), assistant_id=assistant_id)
    assert len(listing["assistants"]) == 1
    entry = listing["assistants"][0]
    assert _SETUP["abilities"] in entry["identity"]
    assert _SETUP["rules"] in entry["rules"]
    assert _SETUP["tone"] in entry["tone"]


@pytest.mark.asyncio
async def test_assistant_setup_is_append_only(runtime):
    """补充设定只能**追加**：原有内容一个字都不能被删改。"""
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
    """改配置要推事件 —— 否则新搭子/新群要等用户手动刷新才出现。

    用户的原话：「我发现了不是没有放在这两处，而是没有自动刷新」。
    """
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
        # 提交群角色同样要推事件：群与搭子两处配置都改了，界面该立刻看到
        await TeamAssignGroupRolesSkill().run(
            _make_ctx(runtime),
            group_id=group["created"]["id"],
            reviewer_id="soulmate",
            advisor_id="LoveBuddy",
        )
        # 事件是**流式**推过来的：等到条数够了再收工，否则会读到"只到了一半"的中间态
        def _counts() -> tuple[int, int]:
            return (
                len([1 for name, _ in events if name == "assistants_changed"]),
                len([1 for name, _ in events if name == "groups_changed"]),
            )

        fired = await wait_for(lambda: _counts() >= (4, 2), timeout=10)

    assert fired, f"没有收到完整的配置变更事件：{[name for name, _ in events]}"
    # 四次 assistants_changed：新建的"资料整理师" + 建群指名的总管 +
    # 被任命成审核员 / 优化顾问的两个搭子
    # 两次 groups_changed：建群一次、提交群角色一次
    assert _counts() == (4, 2)


@pytest.mark.asyncio
async def test_create_group_reports_unknown_members(runtime):
    """成员 id 编造时：够人就跳过并报出来，不够人就明确拒绝。"""
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
    # 我给的两个成员必须在
    assert {"RelationBuddy", "LoveBuddy"} <= set(member_ids)
    # ⚠️ 只认**指名交上来的**总管：其余成员不该被悄悄安上角色，审核员 / 优化顾问也
    # 只认后面 team_assign_group_roles 交上来的 id（/ 09-28 的口径）。
    assert (runtime.assistants.get("RelationBuddy").group_role or "") == "coordinator"
    assert not (runtime.assistants.get("LoveBuddy").group_role or ""), (
        "建群不该给没被指名的人安上角色"
    )
    # 返回体里带上现有搭子清单：把"先查"这一步真的放到模型眼前
    assert created["existing_assistants"]
    # 也不静默：必须把"下一步要提交角色 id，否则开不了讨论"摆在模型眼前
    assert "team_assign_group_roles" in created["next_step"]


# --------------------------------------------------------------------------- #
# 二点六、建群必须指名总管
# --------------------------------------------------------------------------- #
# 原话：「搭子总管不是昵称，默认还是空昵称。让它创建群的时候，它会越俎代庖要承担群总管的
# 职位，但是又不把自己拉进去」。
#
# 根因：谁当总管以前**按发言位次兜底**（首位），模型却照自己的身份以总管自居 —— 它说的
# 分工和群里的实际分工不是一回事。所以总管必须由调用方指名，而且必须在成员里。
@pytest.mark.asyncio
async def test_create_group_requires_coordinator(runtime):
    """缺总管 / 总管不在成员里 / 空白 id 一律拒绝；指名了就真的落成总管。"""
    # ① 缺参数：Pydantic 直接拒绝（连技能体都进不去）
    with pytest.raises(ValidationError):
        GroupCreateParams(name="缺总管的群", member_ids=["RelationBuddy", "LoveBuddy"])

    # ② 自称总管却不在成员里 → 明确拒绝，并指出"要自己当就先把你自己写进成员"
    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateGroupSkill().run(
            _make_ctx(runtime, assistant_id="BuddyManager"),
            name="自任总管的群",
            member_ids=["RelationBuddy", "LoveBuddy"],
            coordinator_id="BuddyManager",
        )
    assert "member_ids" in str(exc.value)
    assert "自己" in str(exc.value)

    # ③ 空白 id 也拒绝（不能用空格糊过去）
    with pytest.raises(SkillExecutionError):
        await TeamCreateGroupSkill().run(
            _make_ctx(runtime),
            name="空白总管的群",
            member_ids=["RelationBuddy", "LoveBuddy"],
            coordinator_id="   ",
        )

    # ④ 指名的人也在成员里 → 建群成功，总管**写进档案**（讨论时才按它分工），
    #    并且返回体如实告诉模型谁才是总管
    result = await TeamCreateGroupSkill().run(
        _make_ctx(runtime, assistant_id="BuddyManager"),
        name="总管在群里的群",
        member_ids=["BuddyManager", "RelationBuddy", "LoveBuddy"],
        coordinator_id="BuddyManager",
    )
    created = result["created"]
    assert created["coordinator"]["id"] == "BuddyManager"
    assert runtime.groups.get(created["id"]).coordinator_id == "BuddyManager"
    assert (runtime.assistants.get("BuddyManager").group_role or "") == "coordinator"
    assert created["coordinator"]["name"] in result["message"]


@pytest.mark.asyncio
async def test_create_group_coordinator_cannot_steal_other_role(runtime):
    """已经是别的角色（审核员 / 优化顾问）的搭子不能被指成总管 —— 角色不能被无声顶掉。"""
    first = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="第一组",
        member_ids=["RelationBuddy", "LoveBuddy"],
        coordinator_id="RelationBuddy",
    )
    await TeamAssignGroupRolesSkill().run(
        _make_ctx(runtime),
        group_id=first["created"]["id"],
        reviewer_id="LoveBuddy",
        advisor_id="soulmate",
    )
    assert (runtime.assistants.get("LoveBuddy").group_role or "") == "reviewer"

    with pytest.raises(SkillExecutionError) as exc:
        await TeamCreateGroupSkill().run(
            _make_ctx(runtime),
            name="第二组",
            member_ids=["LoveBuddy", "soulmate"],
            coordinator_id="LoveBuddy",
        )
    assert "审核员" in str(exc.value)


@pytest.mark.asyncio
async def test_remove_coordinator_clears_the_group_field(runtime):
    """总管被移出群之后，本群不再挂着他的名字（分工里他已经不发言了）。"""
    created = await TeamCreateGroupSkill().run(
        _make_ctx(runtime),
        name="换人组",
        member_ids=["RelationBuddy", "LoveBuddy", "soulmate"],
        coordinator_id="RelationBuddy",
    )
    group_id = created["created"]["id"]

    result = await TeamUpdateGroupSkill().run(
        _make_ctx(runtime),
        group_id=group_id,
        remove_member_ids=["RelationBuddy"],
    )
    assert runtime.groups.get(group_id).coordinator_id == ""
    assert "总管" in result["message"]


# --------------------------------------------------------------------------- #
# 一·五、群角色确认（AI 不能跳过审核员 / 优化顾问）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_discussion_is_refused_until_roles_are_submitted(runtime, client):
    """没提交审核员 / 优化顾问的 id 之前，开讨论必须被**拒绝**。

    这条钉的就是用户截到的那个口子：以前"要不要审核员"是建群参数，模型一句
    ``require_reviewer=false`` 就带过去了。现在闸门落在开讨论这一步 ——
    所以"建完群直接开讨论"这条路走不通，必须回去交 id。
    """
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
    """提交的角色必须是**真搭子**：编的 id、同一个人顶两个角色都要被拒。"""
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

    # 拒了三次之后，群里依旧是"没配齐"（拒绝不能留下半个状态）
    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert not stored.roles_ready()


@pytest.mark.asyncio
async def test_confirmed_roles_are_remembered_and_invalidated(runtime, client):
    """提交后：记进群配置 + 写进搭子档案 + 推事件；角色被移出群后确认作废。

    "作废"这一半很关键：只认字段的话，闸门会放行一个**已经不在群里**的审核员
    （讨论时他根本不发言），等于角色看着齐、实际没有。
    """
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

    # **不静默**：谁担任了什么角色，必须出现在返回体里（两处配置都改了，两处都要推事件）
    assert fired, f"配置改了就推事件，收到的是：{[name for name, _ in events]}"
    assert confirmed["confirmed"]["roles"]["reviewer"]["id"] == "LoveBuddy"
    assert confirmed["confirmed"]["roles"]["advisor"]["id"] == "RelationBuddy"

    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert stored.roles_ready()
    assert (stored.reviewer_id, stored.advisor_id) == ("LoveBuddy", "RelationBuddy")
    # 档案上的角色同步落下：讨论按它分工（只靠发言位次兜底的话，顺序一变角色就飘了）
    assert runtime.assistants.get("LoveBuddy").group_role == "reviewer"
    assert runtime.assistants.get("RelationBuddy").group_role == "advisor"

    # 把已确认的审核员移出群 → 该角色的确认必须清掉，并如实说明
    updated = await TeamUpdateGroupSkill().run(
        _make_ctx(runtime), group_id=group["id"], remove_member_ids=["LoveBuddy"]
    )
    assert updated["group"]["roles_cleared"] == ["审核员"]
    assert "team_assign_group_roles" in updated["group"]["next_step"]
    # 技能返回给模型的**话术**里也要说（模型读的是 message，不是子字典）
    assert "team_assign_group_roles" in updated["message"]

    stored = next(item for item in runtime.groups.groups if item.id == group["id"])
    assert not stored.roles_ready()

    install_fake_model(runtime, FakeLLM(["不该跑到这里"]))
    with pytest.raises(SkillExecutionError) as exc:
        await TeamStartDiscussionSkill().run(
            _make_ctx(runtime), topic="再来一次", group_id=group["id"]
        )
    # 作废后闸门重新拦住（提示按"缺哪个角色"给，并要求把 id 补回来）
    assert "审核员" in str(exc.value)
    assert "team_assign_group_roles" in str(exc.value)


# --------------------------------------------------------------------------- #
# 二、后台讨论
# --------------------------------------------------------------------------- #
_DISCUSS_SCRIPT = [
    # RelationBuddy：先调一次高危技能，再发言并发起结束投票
    LLMResponse(
        content="",
        tool_calls=[tool_call("dangerous_op", {})],
        finish_reason="tool_calls",
    ),
    "已经清过了。\n[END_VOTE]",
    # LoveBuddy：同意结束
    "同意结束。\n[AGREE]",
    # 发起人做总结
    "结论：数据已清空，建议下周再复核一次。",
]


@pytest.mark.asyncio
async def test_background_discussion_delivers_and_runs_admin_skill(runtime, client):
    """后台讨论：admin 级真的跑，结论写回发起它的那条会话。"""
    calls: list[str] = []
    _register_probe(runtime, calls)
    install_fake_model(runtime, FakeLLM(list(_DISCUSS_SCRIPT)))
    session = (await client.post("/v1/sessions", json={"title": "发起讨论"})).json()
    # 角色必须先提交 —— 这是本次新加的、绕不过去的一步
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

    # ① 高危技能在后台**真的被执行**（本次的核心口径：无人值守下没人能点「允许」）
    assert calls == ["dangerous_op"]

    # ② 结论写回**发起它的那条会话**（用户不必去别处找）
    messages = (await client.get(f"/v1/sessions/{session['id']}/messages")).json()["messages"]
    assert messages, "结果必须落在会话里，否则重启后就找不到了"
    assert "结论" in messages[-1]["content"]

    # ③ 事件里有"开始了"（只读观察窗据此自动弹出）与"结束了"
    kinds = [name for name, _ in events]
    assert "group_task_started" in kinds
    done = next(data for name, data in events if name == "group_task_done")
    assert done["outcome"] == "done"
    assert done["session_id"] == session["id"]
    assert done["group_id"] == group["id"]

    # ④ 讨论过程**落库**：切页面 / 重启后还能看到完整过程
    stored = (await client.get(f"/v1/groups/{group['id']}/messages")).json()["events"]
    assert any(item["event"] == "message" for item in stored)
    assert any(item["event"] == "summary" for item in stored)


@pytest.mark.asyncio
async def test_foreground_discussion_still_refuses_admin_skill(runtime, client):
    """对照：**前台**群讨论不放开 admin —— 有人能点确认的地方不静默执行高危操作。

    这条是"只对后台放开"这个边界的安全钉子，别为了让它变绿而改实现。
    """
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

    # 被拒也不能是"静悄悄什么都没发生"：拒绝原因要回到**模型手里**，
    # 它才知道换个说法继续（群讨论流本身不转发工具事件，所以这里直接看模型看到的消息）
    tool_messages = [
        message for call in llm.calls for message in call if message.role == "tool"
    ]
    assert any(
        "未开启" in (message.content or "") for message in tool_messages
    ), "拒绝的原因必须作为工具结果回到模型手里"


# --------------------------------------------------------------------------- #
# 三、必装技能 + 策划类规则
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_coordinator_gets_required_skills_and_rules(runtime):
    """策划类总管（coordinator）必装 ai_thinking_mode + team_restructure，且 RULES 里
    系统强加「策划前用 ai_thinking_mode、策划后用 team_restructure 重塑团队」两条条款。"""
    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime),
        name="小红书策划师",
        description="负责选题策划",
        group_role="coordinator",
        skills=["kb_search"],
        **_SETUP,
    )
    created = result["created"]
    # ⚠️ 起不再"补装必装技能"：`self_growth` / `ai_thinking_mode` 都划进
    # 「内置技能」（每个搭子恒有），而 `team_restructure` 是搭子总管的**专属技能**，
    # 自定义搭子本来就拿不到 —— 于是这一项从"补装清单"变成了固定说明。
    assert created["required_skills"] == "已包含在内置技能中（每个搭子都有）"

    profile = runtime.assistants.get(created["id"])
    assert profile is not None
    # 白名单里只留 AI 勾的那几个（必装的那些走"内置技能"，不再写进白名单）
    assert profile.enabled_skills == ["kb_search"]

    rules = read_file(runtime.paths, created["id"], RULES_FILE)
    assert "ai_thinking_mode" in rules
    assert "team_restructure" in rules
    assert any("ai_thinking_mode" in item for item in created["imposed_rules"])


@pytest.mark.asyncio
async def test_advisor_gets_thinking_rule_only(runtime):
    """优化顾问（advisor）只强加 ai_thinking_mode 条款，不强加团队重塑。"""
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
    """非策划类搭子不强制**策划类**条款 —— 但会拿到「全员进化」那一节。

    ⚠️ 口径变化：这条用例原来断言"完全没有任何强加规则"。
    现在每个自建搭子都会拿到一段「全员进化」初始规则（内置搭子由系统预置进化任务，
    自建搭子没有，只能靠这段规则让它在对话里主动问用户），所以断言收窄成"**只**有这一段"。
    """
    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime), name="周报助手", description="写周报", **_SETUP
    )
    created = result["created"]
    rules = read_file(runtime.paths, created["id"], RULES_FILE)
    # 策划类条款一条都不该有（这条是原用例的本意，必须保住）
    assert "ai_thinking_mode" not in rules
    assert "team_restructure" not in rules
    # 但「全员进化」这段必须在，而且要带上它自己的名字（任务名格式靠它落地）
    assert evolution.SECTION_TITLE in rules
    assert evolution.task_name("周报助手") in rules
    imposed = created["imposed_rules"]
    assert len(imposed) == 1
    assert evolution.SECTION_TITLE in imposed[0]


@pytest.mark.asyncio
async def test_ensure_required_skills_backfills(runtime):
    """team_ensure_required_skills 兜底：对已建好的策划类搭子统一补必装 + 强加规则。"""
    from my_agent.assistants.persona import write_file

    result = await TeamCreateAssistantSkill().run(
        _make_ctx(runtime),
        name="策划师二号",
        description="负责策划",
        group_role="coordinator",
        skills=["kb_search"],
        **_SETUP,
    )
    assistant_id = result["created"]["id"]
    # 模拟"之前建的搭子缺了必装、规则也缺了条款"：收窄技能 + 覆盖掉 RULES
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
    assert set(item["added_skills"]) >= {"self_growth", "ai_thinking_mode", "team_restructure"}
    assert any("ai_thinking_mode" in r for r in item["imposed_rules"])

    profile2 = runtime.assistants.get(assistant_id)
    assert profile2 is not None
    assert set(profile2.enabled_skills) >= {"kb_search", "self_growth", "ai_thinking_mode", "team_restructure"}
    rules = read_file(runtime.paths, assistant_id, RULES_FILE)
    assert "ai_thinking_mode" in rules
    assert "team_restructure" in rules


# --------------------------------------------------------------------------- #
# 四、暂停任务（观察窗「暂停任务」按钮）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_stop_discussion_cancels_task(runtime):
    """stop_discussion 取消在跑的 task，之后返回 stopped=False（观察窗「暂停任务」的落点）。"""
    async def _slow() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(_slow())
    runtime.orchestrator._tasks["grp-test"] = task  # noqa: SLF001

    result = await runtime.orchestrator.stop_discussion("grp-test")
    assert result["stopped"] is True
    with pytest.raises(asyncio.CancelledError):
        await task

    again = await runtime.orchestrator.stop_discussion("grp-test")
    assert again["stopped"] is False


@pytest.mark.asyncio
async def test_stop_route_reports_not_running(runtime, client):
    """没在跑的群 / 不存在的群，stop 路由返回 stopped=False 或 404，不算错误。"""
    group = await _create_group(client, name="停一个没在跑的群")
    resp = await client.post(f"/v1/groups/{group['id']}/stop")
    assert resp.status_code == 200
    assert resp.json() == {"group_id": group["id"], "stopped": False}

    missing = await client.post("/v1/groups/不存在的群/stop")
    assert missing.status_code == 404


# --------------------------------------------------------------------------- #
# 六、「先查官网，再自建」：这是**闸门**，不是工具描述里的一句话
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_needs_library_check_first(runtime):
    """没查过官网搭子库就直接建搭子 / 建群 → 被拒绝，并被告知先去查。

    产品约定：AI 要新建搭子 / 建群之前，先看官网有没有合适的
    （有就导进来、没有才自己建）。只写在工具描述里是没用的 —— 模型照样会直接建，
    所以做成硬闸门（与"必须先提交审核员 id"同一个教训）。
    """
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
    """导入这条路不受闸门约束 —— 包本身就是"已经用上现成的了"。

    （用户上传的包、或从官网拉下来的包都走这条路；再要求先查一遍没有意义。）
    """
    runtime.buddy_library.checked = False

    created = await runtime.orchestrator.create_assistant(
        name="导入来的搭子", description="从包里来的", from_import=True
    )

    assert runtime.assistants.get(created["id"]) is not None


# --------------------------------------------------------------------------- #
# 群对话：AI 也能建 / 改名 / 清空 / 删除
# --------------------------------------------------------------------------- #
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
    """`team_list_assistants` 必须列出群**有哪些对话**，id 与标题都有。

    少了它，AI 想改名 / 清空 / 删除某条对话时只能靠"最近一条"猜 ——
    而猜错一条就是把用户另一条对话动了，界面上没有任何提示。

    ⚠️ 判据是"**建了一条之后**清单里能看到它"，而不是"新群的 threads 非空"：
    刚建出来的群本来就没有对话（`GroupThreadRepository` 只在第一次拉列表时兜底
    建一条，而这里是直接读库）。测试要贴着这个真实语义写。
    """
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
    """四个技能串起来走一遍：建 → 改名 → 清空 → 删除。

    ⚠️ 建**两条**：删除那条拒绝"删掉群里最后一条对话"，只建一条的话
    最后一步注定被拒 —— 那是另一条用例（见下）在考的事。
    """
    group_id = await _make_group(runtime)
    ctx = _make_ctx(runtime)

    created = await TeamCreateGroupThreadSkill().run(ctx, group_id=group_id, title="预算复盘")
    thread_id = created["thread"]["id"]
    assert created["thread"]["title"] == "预算复盘"
    # 第二条：用来把"删最后一条"那条规则让开
    await TeamCreateGroupThreadSkill().run(ctx, group_id=group_id, title="另一条留着")

    # 往里写一条记录，好让"清空"有东西可清
    await runtime.group_event_repo.append(group_id, thread_id, "topic", {"content": "聊预算"})
    assert len(await runtime.group_event_repo.list_events(group_id, thread_id)) == 1

    # 改名
    renamed = await TeamRenameGroupThreadSkill().run(
        ctx, group_id=group_id, thread_id=thread_id, title="预算复盘（第二轮）"
    )
    assert renamed["after"] == "预算复盘（第二轮）"

    # 清空：记录没了，**对话还在**
    cleared = await TeamClearGroupThreadSkill().run(ctx, group_id=group_id, thread_id=thread_id)
    assert cleared["removed"] == 1
    assert await runtime.group_event_repo.list_events(group_id, thread_id) == []
    assert await runtime.group_thread_repo.get(group_id, thread_id) is not None

    # 删除：连带记录一起走
    deleted = await TeamDeleteGroupThreadSkill().run(ctx, group_id=group_id, thread_id=thread_id)
    assert deleted["deleted_title"] == "预算复盘（第二轮）"
    assert await runtime.group_thread_repo.get(group_id, thread_id) is None
    assert deleted["remaining"] == 1, "另一条应当还在"


@pytest.mark.asyncio
async def test_最后一条群对话删不掉(runtime, client):
    """⚠️ 一个群至少要留一条对话。

    删空了的话用户点进这个群是一片空白，而群列表里那条还在 ——
    界面上没有任何"再建一条"的线索。想清内容就用"清空"（对话还在，能接着聊）。
    """
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
    """⚠️ **群 id 与对话 id 必须同时对上**。

    只按 `thread_id` 找的话，模型把两个 id 搞混（A 群的 group_id + B 群的
    thread_id）时依然能改到 B 群那条，而它以为在改 A 群 —— 用户看到的是
    "另一条对话被改了名"，且没有任何提示。
    """
    group_a = await _make_group(runtime, name="甲群")
    group_b = await _make_group(runtime, name="乙群")
    # 乙群里先有真的一条对话（新群本身是空的）
    made = await TeamCreateGroupThreadSkill().run(
        _make_ctx(runtime), group_id=group_b, title="乙群的对话"
    )
    thread_b = made["thread"]

    with pytest.raises(SkillExecutionError):
        await TeamRenameGroupThreadSkill().run(
            _make_ctx(runtime), group_id=group_a, thread_id=thread_b["id"], title="改错了"
        )

    # 乙群那条必须**一点没动**
    assert (await runtime.group_thread_repo.get(group_b, thread_b["id"]))["title"] == "乙群的对话"


@pytest.mark.asyncio
async def test_群对话变动会广播(runtime, client):
    """改完之后要发 `group_threads_changed`。

    复用 `groups_changed` 是**不够**的：那条在界面上的动作是重拉**群**清单，
    而对话列表是"选中某个群之后"才去拉的 —— 用户正开着的那个列表不会刷新，
    他会以为 AI 什么都没做。
    """
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
