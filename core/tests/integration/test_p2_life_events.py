"""P2 集成测试：生活数据接口、全局事件推送、路径白名单。

事件推送是**长连接**，测试里用后台任务收集，主线程去触发，再等条件满足；
直接 `async for` 会在没有事件时永久挂住。
"""

from __future__ import annotations

import time

import pytest

from my_agent.llm.base import LLMResponse
from my_agent.security.paths import PathPolicy
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.office.excel import ExcelReadSkill

# event_collector / wait_for 是长连接测试的公共工具，放在 integration/conftest.py
from .conftest import (
    FakeLLM,
    event_collector,
    install_fake_model,
    make_client,
    read_sse,
    tool_call,
    wait_for,
)


# --------------------------------------------------------------------------- #
# 提醒
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_reminder_crud(runtime, client):
    created = await runtime.reminder_repo.create(
        content="交周报", remind_at=time.time() + 3600, base_at=time.time() + 3600
    )

    listed = (await client.get("/v1/reminders")).json()
    assert listed["pending"] == 1
    assert listed["reminders"][0]["content"] == "交周报"
    # 界面需要可直接展示的时间文本，不该让它自己格式化时间戳
    assert listed["reminders"][0]["remind_at_text"]

    assert (await client.delete(f"/v1/reminders/{created.id}")).json()["ok"] is True
    assert (await client.get("/v1/reminders")).json()["reminders"] == []
    assert (await client.delete(f"/v1/reminders/{created.id}")).status_code == 404


@pytest.mark.asyncio
async def test_due_reminder_is_pushed_to_event_stream(runtime, client):
    """提醒到点必须主动推给客户端 —— 这正是不走 /v1/chat 的原因。"""
    async with event_collector(client) as events:
        await runtime.reminder_repo.create(
            content="该喝水了", remind_at=time.time() - 5, base_at=time.time()
        )
        fired = (await client.post("/v1/reminders/check")).json()
        assert fired["fired"] == 1

        assert await wait_for(lambda: any(e[0] == "reminder" for e in events))

    reminder = next(data for name, data in events if name == "reminder")
    assert reminder["content"] == "该喝水了"
    assert reminder["remind_at_text"]


@pytest.mark.asyncio
async def test_manual_notice_event(runtime, client):
    async with event_collector(client) as events:
        result = (await client.post("/v1/events/test")).json()
        assert result["delivered"] >= 1
        assert await wait_for(lambda: any(e[0] == "notice" for e in events))

    notice = next(data for name, data in events if name == "notice")
    assert notice["title"] == "测试通知"


@pytest.mark.asyncio
async def test_event_stream_requires_auth(base_url):
    async with make_client(base_url, token="wrong") as bad:
        response = await bad.get("/v1/events")
        assert response.status_code == 401


# --------------------------------------------------------------------------- #
# 记账
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_expense_endpoints(runtime, client):
    await runtime.expense_repo.add(amount=35, note="午饭")
    await runtime.expense_repo.add(amount=20, note="打车")

    body = (await client.get("/v1/expenses?period=month")).json()
    assert body["summary"]["total"] == 55
    assert body["summary"]["count"] == 2
    assert len(body["expenses"]) == 2
    assert "餐饮" in body["categories"]

    target = body["expenses"][0]["id"]
    assert (await client.delete(f"/v1/expenses/{target}")).json()["ok"] is True
    assert (await client.delete(f"/v1/expenses/{target}")).status_code == 404
    assert (await client.get("/v1/expenses")).json()["summary"]["count"] == 1


@pytest.mark.asyncio
async def test_expense_endpoint_rejects_bad_period(client):
    response = await client.get("/v1/expenses?period=本季度")
    assert response.status_code == 422
    assert "无法识别的周期" in response.json()["detail"]


@pytest.mark.asyncio
async def test_life_endpoints_report_memory_mode(runtime, client, monkeypatch):
    """数据库不可用时应给出可理解的说明，而不是 500。"""
    runtime.db_ready = False
    response = await client.get("/v1/reminders")
    assert response.status_code == 503
    assert "内存模式" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 路径白名单（HTTP 层）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_paths_endpoint_exposes_whitelist(client, tmp_path):
    body = (await client.get("/v1/paths")).json()
    assert body["allowed_dirs"]
    assert "workspace" in body["allowed_dirs"][0] or body["workspace"] in body["allowed_dirs"]
    # 默认没有额外配置白名单 → 不限制
    assert body["restricted"] is False


@pytest.mark.asyncio
async def test_whitelist_blocks_skill_file_access(runtime, client, tmp_path):
    """配了白名单后，技能读写范围之外的文件必须被拒绝，且报错要能指导用户。"""
    runtime.skills.register(ExcelReadSkill)

    restricted = tmp_path / "只允许这里"
    restricted.mkdir()
    runtime.path_policy = PathPolicy(
        [str(restricted)],
        always_allowed=[runtime.paths.workspace_dir, runtime.paths.artifacts_dir],
    )

    outside = tmp_path / "机密.xlsx"
    outside.write_bytes(b"not a real xlsx")

    # ⚠️ `excel_read` 属「通用技能」：搭子要**勾选**才可见、才可调（四分类）。
    # 不勾的话它会先被"不在本会话启用的技能范围内"拦下，测到的就不是文件白名单了。
    created = await client.post(
        "/v1/assistants",
        json={
            "id": "whitelist-probe",
            "name": "白名单探针",
            "emoji": "🧪",
            "description": "验证技能的文件访问白名单",
            "system_prompt": "你是测试助手",
            "model_id": "",
            "temperature": 0.5,
            "max_iterations": 3,
            "enabled_skills": ["excel_read"],
            "confirm_mode": None,
        },
    )
    assert created.status_code == 200, created.text

    install_fake_model(
        runtime,
        FakeLLM(
            [
                LLMResponse(
                    tool_calls=[tool_call("excel_read", {"file_path": str(outside)})],
                    finish_reason="tool_calls",
                ),
                "好的，我没有权限读取该文件。",
            ]
        ),
    )

    events = await read_sse(
        client, {"message": "读一下这个表", "model_id": "fake", "assistant_id": "whitelist-probe"}
    )
    result = next(data for name, data in events if name == "tool_result")
    assert result["status"] == "error"
    assert "白名单之外" in result["result"]
    # 报错要能指导用户去改设置，而不是一句"失败了"
    assert "设置" in result["result"]


@pytest.mark.asyncio
async def test_whitelist_allows_configured_dir(runtime, client, tmp_path):
    from my_agent.errors import PathNotAllowedError

    allowed = tmp_path / "允许目录"
    allowed.mkdir()
    runtime.path_policy = PathPolicy([str(allowed)])

    ctx = SkillContext(path_policy=runtime.path_policy)
    assert ctx.resolve_path(str(allowed / "a.txt")).name == "a.txt"
    with pytest.raises(PathNotAllowedError):
        ctx.resolve_path(str(tmp_path / "其他" / "b.txt"))
