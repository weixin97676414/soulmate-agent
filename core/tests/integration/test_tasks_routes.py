"""定时任务接口：增删改查走真实 HTTP。

为什么要有这一组：任务**同时是配置**（落在 settings.json 里）。之前只能整份
读-改-写 settings，任何一次并发保存都会把对方的改动吞掉；现在每条改动各有接口，
就必须验证"改一条不会顺手把别的任务清掉"这件事。
"""

from __future__ import annotations

import pytest

from my_agent.config.schemas import ScheduledTaskSpec
from my_agent.llm.base import LLMResponse
from tests.conftest import FakeLLM, tool_call

from .conftest import event_collector, install_fake_model, wait_for


def _draft(**overrides) -> dict:
    payload = {
        "name": "早报",
        "prompt": "汇总今天的行业新闻",
        "trigger": "daily",
        "at_time": "08:30",
        "enabled": True,
    }
    payload.update(overrides)
    return payload


async def _items(client) -> list[dict]:
    return (await client.get("/v1/tasks")).json()["items"]


def _find(items: list[dict], task_id: str) -> dict:
    """按 id 找那条任务。

    ⚠️ 别用 ``items[0]``：运行时启动时会**自动播种**四条内置搭子的「全员进化」任务
    （见 ``runtime.seed_evolution_tasks``），列表里本来就住着别人。
    """
    found = next((item for item in items if item["id"] == task_id), None)
    assert found is not None, f"列表里没有 {task_id}：{[item['id'] for item in items]}"
    return found


@pytest.mark.asyncio
async def test_create_list_update_delete(client):
    created = (await client.post("/v1/tasks", json=_draft())).json()
    task = created["task"]
    assert task["id"]
    assert task["trigger"] == "daily"

    mine = _find(await _items(client), task["id"])
    # 界面要靠这两个字段显示"还有多久到点"和"条件基线建好没有"
    assert "next_run_in_seconds" in mine
    assert mine["condition_ready"] is False
    # 用户手工建的一律不锁
    assert mine["locked"] is False

    updated = (
        await client.put(
            f"/v1/tasks/{task['id']}",
            json=_draft(name="晚报", prompt="汇总今天的行业新闻", at_time="20:30"),
        )
    ).json()
    assert updated["task"]["name"] == "晚报"
    assert updated["task"]["at_time"] == "20:30"
    assert updated["task"]["id"] == task["id"]

    deleted = (await client.delete(f"/v1/tasks/{task['id']}")).json()
    assert deleted["deleted"] == task["id"]
    assert task["id"] not in {item["id"] for item in await _items(client)}


@pytest.mark.asyncio
async def test_second_task_does_not_erase_the_first(client):
    """新增第二条时不能把第一条挤掉 —— 这是"整份读改写"最容易出的错。"""
    first = (await client.post("/v1/tasks", json=_draft(name="甲"))).json()["task"]
    second = (await client.post("/v1/tasks", json=_draft(name="乙"))).json()["task"]

    ids = {item["id"] for item in await _items(client)}
    assert {first["id"], second["id"]} <= ids


@pytest.mark.asyncio
async def test_settings_save_does_not_wipe_tasks(client):
    """保存设置页不能把定时任务抹掉。

    设置页提交的是**整份** settings，其中那份 scheduled_tasks 是它打开那一刻的
    快照。用户开着设置页、同时在「定时」页建了任务，自动保存就会把新任务写没 ——
    这类"我建的任务自己消失"的路径必须被钉住。
    """
    before = {item["id"] for item in await _items(client)}
    task = (await client.post("/v1/tasks", json=_draft())).json()["task"]

    settings = (await client.get("/v1/settings")).json()
    settings["agent"]["scheduled_tasks"] = []  # 模拟"打开设置页时的旧快照"
    settings["agent"]["temperature"] = 0.5
    saved = (await client.put("/v1/settings", json=settings)).json()

    assert saved["agent"]["temperature"] == 0.5
    # 保存后应当正好是"保存前那些 + 刚建的那条"，一条不多一条不少
    assert {item["id"] for item in await _items(client)} == before | {task["id"]}


@pytest.mark.asyncio
async def test_builtin_evolution_tasks_are_seeded_on_startup(client):
    """启动时自动补齐四条「全员进化中 X」。

    这是"内置搭子我们创建好、自动进化"这句话的落地：用户什么都没做，
    打开「定时」页就应该看到它们。多播或漏播都不会报错，所以在这里钉住。
    """
    items = await _items(client)
    presets = [item for item in items if item["id"].startswith("builtin-evolve-")]

    assert len(presets) == 4, f"应当正好四条预置任务，实际 {[i['id'] for i in presets]}"
    assert len({item["assistant_id"] for item in presets}) == 4, "一条一个搭子，不能重复"
    for item in presets:
        assert item["name"].startswith("全员进化中 ")
        assert item["interval_minutes"] == 10080
        assert item["enabled"] is True
        assert item["locked"] is True
    # 四条错峰：起始时间两两不同（同一分钟会有四个搭子抢模型）
    assert len({item["start_at"] for item in presets}) == 4


@pytest.mark.asyncio
async def test_invalid_time_is_rejected(client):
    """25:00 这种时刻建进去就会永远不触发，必须在入口就拒掉。"""
    resp = await client.post("/v1/tasks", json=_draft(at_time="25:00"))

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_condition_without_target_is_rejected(client):
    """选了条件却不给目标，任务会静默地永远不跑 —— 同样在入口拒掉。"""
    resp = await client.post("/v1/tasks", json=_draft(condition="url_changed"))

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_task_returns_404(client):
    assert (await client.delete("/v1/tasks/nope")).status_code == 404
    assert (await client.put("/v1/tasks/nope", json=_draft())).status_code == 404
    assert (await client.post("/v1/tasks/nope/run")).status_code == 409


# --------------------------------------------------------------------------- #
# 内置搭子的自动化任务：用户不能改 / 关 / 删（产品约定）
# --------------------------------------------------------------------------- #
async def _seed(runtime, task_id: str, **overrides) -> ScheduledTaskSpec:
    """直接造一条任务，等价于"搭子自己在对话里建"留下的那条。

    不走 HTTP：这几条要验的正是"界面上改不动"，用接口造它反而绕开了被测的前提。
    已经有同 id 的那条（启动时播种的四条）就直接用它，不重复追加。
    """
    existing = list(runtime.config.settings.agent.scheduled_tasks or [])
    found = next((item for item in existing if item.id == task_id), None)
    if found is not None:
        return found
    payload = {
        "id": task_id,
        "name": "全员进化中 Soulmate",
        "prompt": "整理你自己的记忆",
        "assistant_id": "soulmate",
        "trigger": "interval",
        "interval_minutes": 10080,
        "start_at": "2026-10-04T03:07",
        "enabled": True,
        "origin": "builtin",
        "silent": True,
    }
    payload.update(overrides)
    spec = ScheduledTaskSpec(**payload)
    await runtime.save_scheduled_tasks([*existing, spec])
    return spec


@pytest.mark.asyncio
async def test_builtin_task_cannot_be_edited_disabled_or_deleted(runtime, client):
    """预置任务（四条「全员进化中 X」）：改 / 关 / 删一律 409，只能让搭子去调。

    闸门刻意只在**路由层**（搭子改任务走存储层的技能直连，那条路必须畅通，
    否则"用户可以找搭子协商调整"这句承诺就是空的）。这条用例钉住的就是这个分工。
    """
    task_id = "builtin-evolve-soulmate"
    before = _find(await _items(client), task_id)
    # 界面靠这个字段置灰 + 显示"找搭子协商"，服务端只下发结论、不下发判定依据
    assert before["locked"] is True

    assert (
        await client.put(f"/v1/tasks/{task_id}", json=_draft(name="改个名"))
    ).status_code == 409
    assert (
        await client.put(f"/v1/tasks/{task_id}", json=_draft(enabled=False))
    ).status_code == 409
    assert (await client.delete(f"/v1/tasks/{task_id}")).status_code == 409

    # 三次被拒之后它必须**原封不动**地还在（"拒绝了但其实改了一半"是最糟的结果）。
    # 逐字段比而不是整份比：``next_run_in_seconds`` 是每次现算的秒数，
    # 跨过一秒边界就会差 1，拿它当判据等于给自己埋一个偶尔才红的用例。
    after = _find(await _items(client), task_id)
    for field in (
        "name",
        "prompt",
        "assistant_id",
        "trigger",
        "interval_minutes",
        "start_at",
        "enabled",
        "origin",
        "silent",
    ):
        assert after[field] == before[field], f"{field} 被改动了"


@pytest.mark.asyncio
async def test_buddy_created_task_on_a_builtin_buddy_is_locked(runtime, client):
    """内置搭子**自己在对话里建的**任务同样锁住（否则它会建一条用户改不掉的、
    或者反过来用户能改掉它在用的那条）。"""
    await _seed(runtime, "task-abc", origin="agent", silent=False)

    resp = await client.delete("/v1/tasks/task-abc")

    assert resp.status_code == 409
    assert "协商" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_user_task_pointing_at_a_builtin_buddy_is_not_locked(runtime, client):
    """用户自己建的任务**不锁** —— 哪怕指定内置搭子来跑。

    多锁的代价是用户找不到任何解释（界面正常、只是点了没反应），
    所以这条边界必须钉住。
    """
    task = (
        await client.post("/v1/tasks", json=_draft(assistant_id="soulmate", enabled=False))
    ).json()["task"]

    assert _find(await _items(client), task["id"])["locked"] is False

    updated = await client.put(f"/v1/tasks/{task['id']}", json=_draft(name="我的早报"))
    assert updated.status_code == 200
    assert (await client.delete(f"/v1/tasks/{task['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_interface_cannot_declare_its_own_origin(runtime, client):
    """界面传来的 ``origin`` 一律不算数，创建接口写死成 ``user``。

    这个字段决定"能不能改"，让界面自己声明等于把锁的钥匙交出去 ——
    一个被改过的客户端就能建出"谁也改不掉、连用户自己都不行"的任务。
    """
    created = (
        await client.post(
            "/v1/tasks",
            json=_draft(assistant_id="soulmate", origin="builtin", silent=True),
        )
    ).json()["task"]

    assert created["origin"] == "user"
    assert created["silent"] is False
    assert _find(await _items(client), created["id"])["locked"] is False


@pytest.mark.asyncio
async def test_interface_cannot_flip_silent_or_origin_on_update(runtime, client):
    """更新接口也不能改 ``silent`` / ``origin``：一律沿用现存值。

    ``silent`` 被界面回传的默认值洗掉，"跑完不打扰"就会悄悄失效 ——
    而症状只是"它开始弹窗了"，很难联想到是保存时被覆盖的。
    """
    spec = await _seed(runtime, "task-silent", origin="agent", silent=True)
    # 先让这条任务变成"用户可见的"：换一个不锁的搭子，但仍保留 silent
    await runtime.save_scheduled_tasks(
        [spec.model_copy(update={"assistant_id": "my-own", "origin": "agent"})]
    )

    resp = await client.put("/v1/tasks/task-silent", json=_draft(silent=False, origin="user"))

    assert resp.status_code == 200
    assert resp.json()["task"]["silent"] is True
    assert resp.json()["task"]["origin"] == "agent"


@pytest.mark.asyncio
async def test_run_now_on_a_locked_task_is_allowed(runtime, client):
    """锁的是"改配置"，不是"跑"：「立即执行」照旧可用。

    用户看不了那条任务的配置、也改不了，但至少能立刻看一轮结果 ——
    把他也拦掉的话，唯一的办法就只剩"等下一个周日"。
    """
    install_fake_model(runtime, FakeLLM(["这一轮没要改的。"]))
    task_id = "builtin-evolve-soulmate"  # 启动时自动播种的，不用再造一遍

    resp = await client.post(f"/v1/tasks/{task_id}/run")
    assert resp.status_code == 200, resp.text

    def finished() -> bool:
        # 按 id 找：列表里还住着另外三条预置任务，``describe()[0]`` 未必是它
        entry = next(
            item for item in runtime.task_scheduler.describe() if item["id"] == task_id
        )
        return not entry["running"]

    # 等它真的跑完再收尾：留一个悬着的后台任务会干扰后面的用例
    assert await wait_for(finished, timeout=20)


def _register_admin_probe(runtime, calls: list[str], *, name: str = "dangerous_op") -> None:
    """注册一个 **admin（高危）级**技能，执行时往 ``calls`` 里记一笔。

    拿真实执行痕迹断言，而不是拿回复措辞：要证明的是"这个高危技能**真的被执行了**"，
    而模型的措辞每次都可能不一样，用措辞当断言等于给自己埋一个偶尔才红的用例。
    """
    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name=name,
        display_name="清空数据",
        description="清空全部数据（测试用）",
        permission_level="admin",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  # type: ignore[no-untyped-def]
            calls.append(name)
            return "已清空"

    runtime.skills.register(_Probe)


@pytest.mark.asyncio
async def test_scheduled_task_runs_admin_level_skill(runtime, client):
    """定时任务里 **admin（高危）级**技能也照跑 —— 后台无人值守，没人能点「允许」。

    这是刻意的产品选择（用户要求"不管是使用的什么技能和工具，都默认为自动批准"），
    代价是真实的：无人守看时删文件、跑命令这类操作会真的执行。把它钉成行为，
    免得以后有人"顺手加个安全限制"时，不知道自己正在改的是哪条需求。

    对照：同一个技能在单聊 / 群聊里会被拒 —— 守卫自己的 admin 开关写死 False，
    只有定时任务那个 ``SkillContext`` 带了按次开绿灯（`allow_admin=True`）。
    """
    calls: list[str] = []
    _register_admin_probe(runtime, calls)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("dangerous_op", {})],
                    finish_reason="tool_calls",
                ),
                "清完了。",
            ]
        ),
    )

    # ⚠️ 必须**显式指定搭子**，不能靠 ``assistant_id`` 留空去落到默认搭子。
    # 本条要验的是"高危技能在无人值守时真的会执行"（权限闸），而一个技能能不能
    # 被执行还取决于**跑它的搭子**能用哪些技能。
    # RelationBuddy 是内置搭子：它的可用集合 = 全部内置技能 ∪ 自己的专属，
    # 而探测技能（测试自注册、没归过类）按"未登记一律算内置"落进内置桶 ——
    # 所以它对内置搭子可见，这条才验得到权限闸本身。
    # ⚠️ 别把这里理解成"白名单空 = 不限制"：那个口径 已作废
    # （见 skill/groups.py）。
    task = (await client.post("/v1/tasks", json=_draft(assistant_id="RelationBuddy"))).json()["task"]

    async with event_collector(client) as events:
        resp = await client.post(f"/v1/tasks/{task['id']}/run")
        assert resp.status_code == 200, resp.text
        finished = await wait_for(
            lambda: any(
                name in ("scheduled_task_done", "scheduled_task_failed") for name, _ in events
            ),
            timeout=20,
        )

    assert finished, f"任务没跑完，收到的事件：{[name for name, _ in events]}"
    assert calls == ["dangerous_op"], "高危技能在定时任务里应当真的被执行"


@pytest.mark.asyncio
async def test_scheduled_task_records_iterations_and_keeps_its_trace(runtime, client):
    """后台任务要记**真实轮数**，且它的 trace 必须能被查到（第 88 批，L-13 / M-25）。

    这两件事以前都是坏的，而且坏得**看不出来**：

    * `iterations` 恒传 0 ⇒ 用量页上"后台任务跑了多少轮"永远是 0。
      单聊那条路传的是真实轮数，两下一对比更像是"后台根本不统计"。
    * trace 从不入 `TraceStore`（全仓只有单聊会 put）⇒ 界面上给出的 trace_id
      查 `GET /v1/traces/{id}` **必然 404**。而"按 trace 追一次执行"恰恰是排查
      静默失败最直接的那条路，后台任务又是最容易静默失败的一类
      （没人盯着，失败了只有一条通知）。

    ⚠️ 刻意用一个**会执行工具**的脚本：只有真的跑过工具，轮数才可能不是 0，
    否则这条用例对 L-13 一点约束力都没有。
    """
    calls: list[str] = []
    _register_admin_probe(runtime, calls)
    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    content="",
                    tool_calls=[tool_call("dangerous_op", {})],
                    finish_reason="tool_calls",
                ),
                "做完了。",
            ]
        ),
    )
    task = (await client.post("/v1/tasks", json=_draft(assistant_id="RelationBuddy"))).json()["task"]

    resp = await client.post(f"/v1/tasks/{task['id']}/run")
    assert resp.status_code == 200, resp.text
    assert await wait_for(
        lambda: not next(
            item for item in runtime.task_scheduler.describe() if item["id"] == task["id"]
        )["running"],
        timeout=20,
    )

    assert calls == ["dangerous_op"], "探针没真的执行，下面的断言就没有意义"
    record = (await runtime.usage_repo.recent(limit=1))[0]
    # 轮数口径与单聊**完全一致**（第 93 批统一）：取引擎 `done` 事件给的"模型↔工具往返轮数"。
    # 这段脚本是"调一次工具 → 给结论"两轮，所以是 2（不是"工具执行次数"1，也不是写死的 0）。
    assert record["iterations"] == 2
    # trace_id 必须**真的能查到**：以前它写在用量表里，却指向一个取不到的 trace
    assert record["trace_id"], "后台任务的用量记录必须带 trace_id"
    assert runtime.traces.get(record["trace_id"]) is not None, "trace 没有进留存表"
