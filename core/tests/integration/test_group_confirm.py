"""群聊里的确认通道。

用户报的问题是「群聊中的 buddy 使用技能时需要确认，无法弹出确认弹窗，
导致任务无法进行」。根因是构造群成员 Agent 时**没有注入确认通道**，
于是 confirm 级技能必然走到 `permission.py` 的"没有可用的确认通道"分支被拒。

这组用例守四件事（顺序就是它们出错的代价，从高到低）：

1. 群讨论里 confirm 级技能**真的能弹窗**，批准后讨论继续（核心诉求）；
2. 群级「一律批准」打开后不再弹窗 —— 但它**只放行 confirm 级**，admin 级仍要确认；
3. 群级设置（思考强度 / 权限策略）覆盖成员各自的设置；
4. 讨论被叫停时不留悬挂确认（否则用户再触发同一操作会撞上"已有一项待确认"）。
"""

from __future__ import annotations

import asyncio
import json

from my_agent.agent.group_discussion import build_group_agent as _build_group_agent
from my_agent.config.schemas import GroupProfile
from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM, tool_call

from .conftest import event_collector, install_fake_model, wait_for


def register_probe_skill(runtime, calls: list[str], *, name: str = "write_note") -> None:
    """注册一个 confirm 级技能，执行时往 ``calls`` 里记一笔。

    用它而不是断言回复文本：**要证明的是"这个技能真的被执行了"**，
    而模型的措辞每次都可能不一样，拿措辞当断言等于给自己埋一个偶尔才红的用例。
    """
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name=name,
        display_name="写便签",
        description="写一条便签（测试用）",
        permission_level="confirm",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
            calls.append(name)
            return "写入成功"

    runtime.skills.register(_Probe)


async def _create_group(client, *, name: str = "确认测试群") -> dict:
    created = await client.post(
        "/v1/groups",
        json={"name": name, "member_assistant_ids": ["soulmate", "LoveBuddy"]},
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _consume_discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:
    """在后台消费一次群讨论的 SSE 流。"""
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST", f"/v1/groups/{group_id}/discuss", json={"topic": topic}
    ) as resp:
        assert resp.status_code == 200, await resp.aread()
        event = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[len("data: ") :])))
    return events


async def test_group_discuss_asks_for_confirmation_and_continues(runtime, client):
    """群讨论里 confirm 级技能：弹窗 → 批准 → 讨论继续。"""
    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "会议纪要"})],
                finish_reason="tool_calls",
            ),
            "便签写好了。\n[END_VOTE]",
            "同意结束。\n[AGREE]",
            "结论：便签已写好。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client)

    async with event_collector(client) as events:
        discuss = asyncio.create_task(_consume_discuss(client, group["id"], "帮我记一下"))

        asked = await wait_for(
            lambda: any(name == "permission_request" for name, _ in events), timeout=10
        )
        assert asked, f"群聊里没有弹出确认请求，收到的事件：{[n for n, _ in events]}"

        data = next(payload for name, payload in events if name == "permission_request")
        # 确认框必须说清"是谁要做什么"：只有技能名的话，用户在群聊里会一头雾水
        assert data["skill_name"] == "write_note"
        assert data["group_id"] == group["id"]
        assert data["assistant_id"] == "soulmate"

        await client.post(
            "/v1/confirm", json={"request_id": data["request_id"], "approved": True}
        )
        seen = await asyncio.wait_for(discuss, timeout=20)

    assert calls == ["write_note"], "批准之后技能应当真的执行了"
    kinds = [name for name, _ in seen]
    assert "summary" in kinds, f"讨论应当继续到总结：{kinds}"


async def test_group_discuss_denied_keeps_going(runtime, client):
    """拒绝之后讨论**不能崩**。

    技能会被记成"用户拒绝"，模型据此换个说法继续 —— 用户点「拒绝」的意图是
    "别做这件事"，而不是"把这场讨论废掉"。
    """
    calls: list[str] = []
    register_probe_skill(runtime, calls, name="write_note")
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "x"})],
                finish_reason="tool_calls",
            ),
            "那我先不写了，我们继续讨论。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：先不动。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="拒绝测试群")

    async with event_collector(client) as events:
        discuss = asyncio.create_task(_consume_discuss(client, group["id"], "记一下"))
        assert await wait_for(
            lambda: any(name == "permission_request" for name, _ in events), timeout=10
        )
        data = next(payload for name, payload in events if name == "permission_request")
        await client.post(
            "/v1/confirm", json={"request_id": data["request_id"], "approved": False}
        )
        seen = await asyncio.wait_for(discuss, timeout=20)

    assert calls == [], "被拒绝的技能绝不能执行"
    assert "summary" in [name for name, _ in seen], "拒绝不等于讨论中断"


async def test_group_auto_approve_skips_the_dialog(runtime, client):
    """群级「一律批准」：不再弹窗，直接执行。"""
    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "y"})],
                finish_reason="tool_calls",
            ),
            "写好了。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：写好了。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="自动批准群")

    patched = await client.patch(
        f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["confirm_mode"] == "auto_approve"

    async with event_collector(client) as events:
        await _consume_discuss(client, group["id"], "记一下")

    assert calls == ["write_note"], "一律批准时技能应当直接执行"
    assert not [name for name, _ in events if name == "permission_request"], "不该再弹窗"


async def test_group_confirm_does_not_bypass_admin_level(runtime, client):
    """**群级开关不是高危后门**：admin 级操作即使开了「一律批准」也必须确认。

    这条是安全边界，不是体验问题：`permission.py` 只在 confirm 级放行
    auto_approve，这里从群聊侧再钉一遍。
    """
    calls: list[str] = []

    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="danger_delete",
        display_name="删除全部数据",
        description="测试用的高危技能",
        permission_level="admin",
    )
    class _Danger(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
            calls.append("danger_delete")
            return "已删除"

    runtime.skills.register(_Danger)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("danger_delete", {})],
                finish_reason="tool_calls",
            ),
            "好。\n[END_VOTE]",
            "同意。\n[AGREE]",
            "结论：没做。",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="高危群")
    await client.patch(f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"})

    async with event_collector(client) as events:
        await _consume_discuss(client, group["id"], "清空数据")

    assert calls == [], "admin 级绝不能因为群级开关而免确认"
    assert not [name for name, _ in events if name == "permission_request"], (
        "当前实现里 admin 级在未开启该能力时直接拒绝，也不会弹窗"
    )


def test_group_level_settings_override_members(runtime):
    """群级思考强度 / 权限策略覆盖成员各自的设置。"""
    # 构造 Agent 需要能取到模型；这两个用例不跑对话，给个空剧本即可
    install_fake_model(runtime, FakeLLM([]))
    group = make_group("覆盖测试群")
    member = runtime.assistants.get("soulmate")
    assert member is not None

    # 成员自己设了高，但群级设了低 → 群优先
    member = member.model_copy(update={"reasoning_effort": "high"})
    scoped = group.model_copy(update={"reasoning_effort": "low"})

    agent = _build_group_agent(runtime, scoped, member, history=[])
    assert agent.config.reasoning_effort == "low"

    # 群级**显式**留空 → 回落到成员自己的设置。
    #
    # ⚠️ 必须显式传 `None`：出厂默认已经从 `None` 改成了 `"medium"`
    # （"每次创建的新群与新对话，思考强度默认为中"），
    # 所以 `make_group` 造出来的那个群**有值**，不会回落。
    # `None` 仍然合法 —— 界面上选「跟随每个搭子」就是它，只是不再是默认。
    cleared = group.model_copy(update={"reasoning_effort": None})
    fallback = _build_group_agent(runtime, cleared, member, history=[])
    assert fallback.config.reasoning_effort == "high"


def test_group_agent_has_confirm_channel(runtime):
    """群成员 Agent 必须带确认通道（这正是本次修的那个 bug）。"""
    install_fake_model(runtime, FakeLLM([]))
    group = make_group("通道测试群")
    member = runtime.assistants.get("soulmate")
    assert member is not None

    agent = _build_group_agent(runtime, group, member, history=[])
    assert agent.ctx.has_confirm_channel is True

    scoped = group.model_copy(update={"confirm_mode": "auto_approve"})
    scoped_agent = _build_group_agent(runtime, scoped, member, history=[])
    # 群级策略覆盖成员自己的（soulmate 默认交互式）。
    # ⚠️ `ctx.confirm_mode` 现在是**惰性提供者**（任务跑到一半改策略要立刻生效，
    # 见 PermissionGuard.effective_mode），所以这里断言"实际生效值"而不是那个字段。
    assert runtime.skills.guard.effective_mode(scoped_agent.ctx) == "auto_approve"


async def test_group_patch_supports_partial_updates(client):
    """PATCH 是局部更新：只改传进来的字段，且空串 = 清回默认。"""
    group = await _create_group(client, name="补丁群")

    first = await client.patch(
        f"/v1/groups/{group['id']}",
        json={"reasoning_effort": "high", "confirm_mode": "auto_approve"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["reasoning_effort"] == "high"
    assert first.json()["confirm_mode"] == "auto_approve"
    # 名字没提就不该动
    assert first.json()["name"] == "补丁群"

    second = await client.patch(
        f"/v1/groups/{group['id']}", json={"reasoning_effort": ""}
    )
    assert second.json()["reasoning_effort"] is None, "空串应当清回「跟随成员」"
    assert second.json()["confirm_mode"] == "auto_approve", "没传的字段不能被顺手清掉"

    unknown = await client.patch("/v1/groups/nope", json={"name": "x"})
    assert unknown.status_code == 404


async def test_cancelled_discussion_leaves_no_pending_confirm(runtime, client):
    """叫停讨论后不能留下悬挂确认。

    留下的后果很具体：用户再触发同一个操作会撞上"已经有一项待确认"，
    而界面上完全看不出为什么没反应 —— 只能等满确认超时。
    """
    calls: list[str] = []
    register_probe_skill(runtime, calls)
    llm = FakeLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[tool_call("write_note", {"text": "z"})],
                finish_reason="tool_calls",
            ),
            "写好了",
        ]
    )
    install_fake_model(runtime, llm)
    group = await _create_group(client, name="取消测试群")

    async with event_collector(client) as events:
        async with client.stream(
            "POST", f"/v1/groups/{group['id']}/discuss", json={"topic": "记一下"}
        ) as resp:
            assert resp.status_code == 200
            assert await wait_for(
                lambda: any(name == "permission_request" for name, _ in events), timeout=10
            )
            assert runtime.pending_confirms, "此刻应当有一个等待中的确认"
            # 用户点「停止」＝前端断开连接，服务端生成器随即被取消
            await resp.aclose()

        assert await wait_for(lambda: not runtime.pending_confirms, timeout=10), (
            "讨论被叫停后，挂起的确认必须被收起"
        )

    assert calls == [], "被叫停的讨论不该把技能跑完"


def make_group(name: str) -> GroupProfile:
    """造一个群对象（不落盘）。

    只关心"Agent 是怎么构造出来的"那几个用例不需要走 HTTP 建群：
    建群会顺带触发配置落盘，而这里要验的是取参数的优先级。
    """
    return GroupProfile(id="g-test", name=name, member_assistant_ids=["soulmate", "LoveBuddy"])


# --------------------------------------------------------------------------- #
# 群设置与单聊设置**不能互相串**（特别强调）
# --------------------------------------------------------------------------- #
async def test_群权限设置不会影响单聊(runtime, client):
    """⚠️ 这条守的是一个**必须一直成立的边界**：

    "单聊的权限设置是管每个搭子在单聊中权限的；群聊的权限设置是管群里每个搭子
    在群聊当中权限的，千万不能搞混。"

    实现上它们读的是**两个不同的字段**（见下面两条断言各自的来源），但这条路径
    太容易被"顺手统一一下"改坏 —— 比如有人觉得"群和单聊应该共用一份权限策略"，
    把群级设置写进搭子档案。那样用户改一个群，单聊里的行为会跟着变，
    而这两个页面看起来毫无关系，他永远查不出是哪里动的手。

    判据是"群改过之后，单聊那条链的取值**一点没变**"，而不是某个具体值：
    `assistant_confirm_mode` 在搭子没设时返回 `None`（= 沿用全局，那条回落由
    `PermissionGuard.effective_mode` 做），所以断言 `None`/`interactive` 都不对 ——
    真正要钉的是"它不受群影响"。
    """
    before = runtime.assistant_confirm_mode("soulmate")

    group = await _create_group(client, name="权限隔离测试群")
    # 群级设成自动批准
    patched = await client.patch(
        f"/v1/groups/{group['id']}", json={"confirm_mode": "auto_approve"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["confirm_mode"] == "auto_approve"

    # 单聊侧：读的是**搭子档案 → 全局**这条链，与刚才那个群毫无关系
    after = runtime.assistant_confirm_mode("soulmate")
    assert after == before, (
        "群级权限设置泄漏到单聊了 —— 单聊读的应当是搭子档案 / 全局，不能读群"
    )
    assert after != "auto_approve", "单聊这边的取值不可能是群刚才设的那个"


async def test_群思考强度默认是中(runtime, client):
    """新建的群默认「中」，不是"跟随每个搭子"。

    为什么值得钉住：`None` = "跟随每个成员自己的设置"，而群成员常常各有各的档位
    （甚至有的没设）—— 新群第一次讨论会想多久，用户完全预料不到。而"思考强度"
    恰恰是他为了**这一次讨论**才去调的东西，得先有个确定的起点。
    """
    group = await _create_group(client, name="思考强度默认值测试群")
    assert group["reasoning_effort"] == "medium"

    # `None` 仍然合法（界面上选"跟随每个搭子"就是它），只是**不再是出厂值**
    cleared = await client.patch(
        f"/v1/groups/{group['id']}", json={"reasoning_effort": ""}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["reasoning_effort"] is None
