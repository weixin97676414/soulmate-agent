"""群聊的团队规则：角色分工、结束投票权限、审核打回、越权可见。

的四条要求落在这里：

1. 群里要有「总管 → 各专职 → 审核员」的分工（角色按档案，缺了按发言位次兜底）；
2. **结束投票只能由发起者（首位发言者）或末序发言者发起**，别人发的一律不受理
   —— 而且要**说出来**，不能静默吞掉；
3. 审核员不达标时 [REJECT] 打回给总管（讨论继续，不额外重开一场）；
4. 越权（用了不在自己白名单里的工具）要在群里**标出来**（不动权限，只看）。
"""

from __future__ import annotations

import json

from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM, tool_call

from .conftest import install_fake_model


async def _create_group(client, *, name: str, members: list[str] | None = None) -> dict:
    created = await client.post(
        "/v1/groups",
        json={
            "name": name,
            "member_assistant_ids": members or ["RelationBuddy", "soulmate", "LoveBuddy"],
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


async def _discuss(client, group_id: str, topic: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", f"/v1/groups/{group_id}/discuss", json={"topic": topic}) as resp:
        assert resp.status_code == 200, await resp.aread()
        current = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                current = line[len("event: ") :]
            elif line.startswith("data: "):
                events.append((current, json.loads(line[len("data: ") :])))
    return events


async def test_only_initiator_or_last_speaker_can_end_vote(runtime, client):
    """中间的搭子写 [END_VOTE] 不算数，而且要被告知规则（不静默）。"""
    install_fake_model(
        runtime,
        FakeLLM(
            [
                "总管先说：这活分给第二位。",  # 首位（有发起权，但这次不发）
                "我也来收个尾。\n[END_VOTE]",  # 中间那位：**没有**发起权
                "同意收尾。\n[AGREE]",  # 末位（有发起权）
                "结论：按上面的来。",
            ]
        ),
    )
    group = await _create_group(client, name="投票权限群")

    events = await _discuss(client, group["id"], "商量一下这周的安排")

    kinds = [name for name, _ in events]
    denied = [data for name, data in events if name == "vote_denied"]
    assert denied, f"中间那位越权发起应当被明确拒绝：{kinds}"
    assert "末序发言者" in denied[0]["reason"]
    assert "vote_request" not in kinds, "被拒的那次不该真的发起投票"


async def test_reviewer_can_reject_and_discussion_continues(runtime, client):
    """审核员 [REJECT] 打回：讨论继续（总管重新安排），而不是就此结束。"""
    install_fake_model(
        runtime,
        FakeLLM(
            [
                "总管：交付内容我安排给别人了。",  # 首位
                "我做完了这部分。",  # 中间执行
                "交付不完整，缺依据。\n[REJECT] 请补上数据来源。",  # 末位=审核员
                "收到，我重新安排并补上来源。",  # 总管下一轮
                "补齐了。",
                "这份可以了。\n[PASS]",
                "结论：已补齐并验收通过。",
            ]
        ),
    )
    group = await _create_group(client, name="审核打回群")

    events = await _discuss(client, group["id"], "做一份材料")

    reviews = [data for name, data in events if name == "review"]
    assert reviews, f"审核结论应当作为事件给出：{[n for n, _ in events]}"
    assert reviews[0]["passed"] is False
    assert "数据来源" in reviews[0]["reason"], "打回理由要带上，总管才有得照着改"
    # 打回之后讨论**继续**（后面还有发言），而不是直接收尾
    assert any(name == "message" for name, _ in events[3:]), "打回后应当继续讨论"


async def test_out_of_scope_is_visible(runtime, client):
    """越权调用会被标出来（用户选的"不动权限、只晾出来"）。"""
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name="only_reviewer_tool",
        display_name="只有审核员该用的工具",
        description="测试用",
        permission_level="safe",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
            return "ok"

    runtime.skills.register(_Probe)
    # ⚠️ 把它标成「我的技能」（source=custom）：否则一个"没登记过"的技能会被判成
    # 「内置技能」（判定是"显式列通用、其余算内置"，见 skill/groups.py），
    # 于是**每个搭子都有它** —— "越权"这个场景就根本构造不出来了。
    runtime.skills.get("only_reviewer_tool").meta.source = "custom"

    install_fake_model(
        runtime,
        FakeLLM(
            [
                # 首位（总管）本来没限定技能白名单 → 不标
                "我来安排。",
                # 第二位被限定了技能白名单，却用了范围外的工具 → 要标出来
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("only_reviewer_tool", {})],
                    finish_reason="tool_calls",
                ),
                "顺手做了。",
                "我看看。\n[PASS]",
                "结论：完成。",
            ]
        ),
    )
    # ⚠️ 中间那位必须用**自建**搭子，不能用内置的：四位内置搭子的可用能力
    # 已经写死，给 soulmate 设白名单会被 409 直接拒掉，
    # 那样测的就不是"越权被标出来"、而是"锁生效了"。
    created = await client.post(
        "/v1/assistants",
        json={"id": "probe", "name": "越权探针", "enabled_skills": ["kb_search"]},
    )
    assert created.status_code == 200, created.text
    group = await _create_group(
        client, name="越权群", members=["RelationBuddy", "probe", "LoveBuddy"]
    )

    events = await _discuss(client, group["id"], "随便做点什么")

    flagged = [data for name, data in events if name == "out_of_scope"]
    assert flagged, f"越权调用应当被标出来：{[name for name, _ in events]}"
    assert flagged[0]["skill"] == "only_reviewer_tool"
    assert flagged[0]["name"], "要说清是谁越的界"
    # "这活本该是谁的"也要给 —— 用户才知道该让谁去做
    assert "owners" in flagged[0]
