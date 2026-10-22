






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
    
    assert "next_run_in_seconds" in mine
    assert mine["condition_ready"] is False
    
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

    first = (await client.post("/v1/tasks", json=_draft(name="甲"))).json()["task"]
    second = (await client.post("/v1/tasks", json=_draft(name="乙"))).json()["task"]

    ids = {item["id"] for item in await _items(client)}
    assert {first["id"], second["id"]} <= ids


@pytest.mark.asyncio
async def test_settings_save_does_not_wipe_tasks(client):






    before = {item["id"] for item in await _items(client)}
    task = (await client.post("/v1/tasks", json=_draft())).json()["task"]

    settings = (await client.get("/v1/settings")).json()
    settings["agent"]["scheduled_tasks"] = []  
    settings["agent"]["temperature"] = 0.5
    saved = (await client.put("/v1/settings", json=settings)).json()

    assert saved["agent"]["temperature"] == 0.5
    
    assert {item["id"] for item in await _items(client)} == before | {task["id"]}


@pytest.mark.asyncio
async def test_builtin_evolution_tasks_are_seeded_on_startup(client):










    items = await _items(client)
    presets = [item for item in items if item["id"].startswith("builtin-evolve-")]
    weekly = [item for item in presets if item["id"] != "builtin-evolve-monthly-review"]
    monthly = [item for item in presets if item["id"] == "builtin-evolve-monthly-review"]

    assert len(presets) == 6, f"应当正好六条预置任务，实际 {[i['id'] for i in presets]}"
    assert len(weekly) == 5, "五条周任务，一条一个搭子"
    assert len({item["assistant_id"] for item in weekly}) == 5, "一条一个搭子，不能重复"
    for item in weekly:
        assert item["name"].startswith("全员进化中 ")
        assert item["interval_minutes"] == 10080
        assert item["enabled"] is True
        assert item["locked"] is True
        assert item["silent"] is True
    
    assert len({item["start_at"] for item in weekly}) == 5

    
    assert len(monthly) == 1
    assert monthly[0]["assistant_id"] == "BuddyManager"
    assert monthly[0]["name"] == "全员进化月度复盘"
    assert monthly[0]["interval_minutes"] == 43200
    assert monthly[0]["silent"] is False
    assert monthly[0]["locked"] is True


@pytest.mark.asyncio
async def test_invalid_time_is_rejected(client):

    resp = await client.post("/v1/tasks", json=_draft(at_time="25:00"))

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_condition_without_target_is_rejected(client):

    resp = await client.post("/v1/tasks", json=_draft(condition="url_changed"))

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_task_returns_404(client):
    assert (await client.delete("/v1/tasks/nope")).status_code == 404
    assert (await client.put("/v1/tasks/nope", json=_draft())).status_code == 404
    assert (await client.post("/v1/tasks/nope/run")).status_code == 409





async def _seed(runtime, task_id: str, **overrides) -> ScheduledTaskSpec:





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





    task_id = "builtin-evolve-soulmate"
    before = _find(await _items(client), task_id)
    
    assert before["locked"] is True

    assert (
        await client.put(f"/v1/tasks/{task_id}", json=_draft(name="改个名"))
    ).status_code == 409
    assert (
        await client.put(f"/v1/tasks/{task_id}", json=_draft(enabled=False))
    ).status_code == 409
    assert (await client.delete(f"/v1/tasks/{task_id}")).status_code == 409

    
    
    
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


    await _seed(runtime, "task-abc", origin="agent", silent=False)

    resp = await client.delete("/v1/tasks/task-abc")

    assert resp.status_code == 409
    assert "协商" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_user_task_pointing_at_a_builtin_buddy_is_not_locked(runtime, client):





    task = (
        await client.post("/v1/tasks", json=_draft(assistant_id="soulmate", enabled=False))
    ).json()["task"]

    assert _find(await _items(client), task["id"])["locked"] is False

    updated = await client.put(f"/v1/tasks/{task['id']}", json=_draft(name="我的早报"))
    assert updated.status_code == 200
    assert (await client.delete(f"/v1/tasks/{task['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_interface_cannot_declare_its_own_origin(runtime, client):





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





    spec = await _seed(runtime, "task-silent", origin="agent", silent=True)
    
    await runtime.save_scheduled_tasks(
        [spec.model_copy(update={"assistant_id": "my-own", "origin": "agent"})]
    )

    resp = await client.put("/v1/tasks/task-silent", json=_draft(silent=False, origin="user"))

    assert resp.status_code == 200
    assert resp.json()["task"]["silent"] is True
    assert resp.json()["task"]["origin"] == "agent"


@pytest.mark.asyncio
async def test_run_now_on_a_locked_task_is_allowed(runtime, client):





    install_fake_model(runtime, FakeLLM(["这一轮没要改的。"]))
    task_id = "builtin-evolve-soulmate"  

    resp = await client.post(f"/v1/tasks/{task_id}/run")
    assert resp.status_code == 200, resp.text

    def finished() -> bool:
        
        entry = next(
            item for item in runtime.task_scheduler.describe() if item["id"] == task_id
        )
        return not entry["running"]

    
    assert await wait_for(finished, timeout=20)


def _register_admin_probe(runtime, calls: list[str], *, name: str = "dangerous_op") -> None:





    from my_agent.skill.base import BaseSkill
    from my_agent.skill.decorator import skill as skill_decorator

    @skill_decorator(
        name=name,
        display_name="清空数据",
        description="清空全部数据（测试用）",
        permission_level="admin",
    )
    class _Probe(BaseSkill):
        async def run(self, ctx, **params):  
            calls.append(name)
            return "已清空"

    runtime.skills.register(_Probe)


@pytest.mark.asyncio
async def test_scheduled_task_runs_admin_level_skill(runtime, client):









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
    
    
    assert record["iterations"] == 2
    
    assert record["trace_id"], "后台任务的用量记录必须带 trace_id"
    assert runtime.traces.get(record["trace_id"]) is not None, "trace 没有进留存表"
