"""AppRuntime 的确认通道与任务管理测试。

重点保护一个容易被忽略的正确性问题：**确认请求必须按会话隔离**。
早期实现里，任何一个会话断开都会调 ``reject_all_pending()``，把其他会话
正在等待用户点击的确认一起拒掉 —— 表现就是"确认弹窗莫名其妙消失了"。
"""

from __future__ import annotations

import asyncio

import pytest

from my_agent.config.paths import AppPaths
from my_agent.security.confirm import ConfirmRequest
from my_agent.server.runtime import AppRuntime


@pytest.fixture
def runtime(tmp_path) -> AppRuntime:
    # ⚠️ 这里**不再**压 ``confirm_timeout_seconds``：那个字段已失效（确认改为
    # 永不超时，见 ``AppRuntime.request_confirm``），压它不会再有任何效果，
    # 留着只会让人以为"测试里超时是 5 秒"。
    return AppRuntime(AppPaths(tmp_path / "data").ensure())


def make_request(request_id: str, skill: str = "write_file") -> ConfirmRequest:
    return ConfirmRequest(
        request_id=request_id,
        skill_name=skill,
        display_name="写入文件",
        description="测试用",
        permission_level="confirm",
        params={"path": "a.txt"},
        prompt="是否继续？",
    )


@pytest.mark.asyncio
async def test_confirm_approved_returns_true(runtime):
    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r1"), emit, owner="A"))
    await asyncio.sleep(0.05)
    assert runtime.resolve_confirm("r1", True) is True
    assert await task is True


@pytest.mark.asyncio
async def test_confirm_denied_returns_false(runtime):
    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r1"), emit, owner="A"))
    await asyncio.sleep(0.05)
    assert runtime.resolve_confirm("r1", False) is True
    assert await task is False


@pytest.mark.asyncio
async def test_resolve_unknown_request_returns_false(runtime):
    assert runtime.resolve_confirm("not-exist", True) is False


@pytest.mark.asyncio
async def test_确认不设超时_没人响应就一直挂着(runtime):
    """⚠️ 这条用例守的是**没有超时**这件事（产品要求）。

    它以前叫 ``test_confirm_timeout_falls_back_to_deny``，守的是**相反**的约定
    （120 秒没响应自动按拒绝）。方向反过来了，所以断言也整个反过来 ——
    把那个"超时"字段设成极短，然后确认它**完全不生效**。
    """
    # 就算把它设成 0.2 秒也不该有任何效果：字段已失效（见 schemas 的说明）
    runtime.config.settings.security.confirm_timeout_seconds = 0.2

    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r1"), emit, owner="A"))
    # 等一段**远大于**那个失效值的时间。若超时还在生效，任务早就该以 False 结束了
    await asyncio.sleep(0.6)
    assert not task.done(), "确认不该自己结束 —— 只有收到响应或被打断才能收尾"
    assert "r1" in runtime.pending_confirms, "挂起表里要留着它，否则没人能再回传结果"

    # 真的响应了，它才动
    assert runtime.resolve_confirm("r1", True) is True
    assert await task is True
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_任务被打断时确认作废(runtime):
    """停止 / 关会话时挂起的确认必须作废。

    这是现在**唯一**的收尾路径（没有超时兜底了），所以它必须有测试跟着。
    """

    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r2"), emit, owner="A"))
    await asyncio.sleep(0)  # 让 emit 跑起来，确认已登记
    assert runtime.reject_pending(owner="A") == 1
    assert await task is False
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_别的会话被打断时不影响我的确认(runtime):
    """``owner`` 要真的起作用：一个会话被停掉，不该把另一个会话的确认一起拒掉。"""

    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r3"), emit, owner="A"))
    await asyncio.sleep(0)
    # 停的是 B，A 的确认必须还在等
    assert runtime.reject_pending(owner="B") == 0
    assert not task.done()
    assert runtime.resolve_confirm("r3", False) is True
    assert await task is False


@pytest.mark.asyncio
async def test_reject_pending_is_scoped_to_owner(runtime):
    """拒绝 A 会话的确认，不能连带拒掉 B 会话正在等待的确认。"""
    emitted: list[str] = []

    async def emit(request: ConfirmRequest):
        emitted.append(request.request_id)

    task_a = asyncio.create_task(runtime.request_confirm(make_request("a1"), emit, owner="A"))
    task_b = asyncio.create_task(runtime.request_confirm(make_request("b1"), emit, owner="B"))
    await asyncio.sleep(0.05)

    assert set(runtime.pending_confirms) == {"a1", "b1"}

    runtime.reject_pending("A")
    assert await task_a is False
    # B 的确认必须仍然挂在那里
    assert "b1" in runtime.pending_confirms
    assert not task_b.done()

    runtime.reject_pending("B")
    assert await task_b is False
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_reject_all_when_owner_omitted(runtime):
    async def emit(_request):
        return None

    tasks = [
        asyncio.create_task(runtime.request_confirm(make_request(f"r{i}"), emit, owner=owner))
        for i, owner in enumerate(["A", "B", "C"])
    ]
    await asyncio.sleep(0.05)
    assert runtime.reject_pending() == 3
    assert all(await asyncio.gather(*tasks)) is False


@pytest.mark.asyncio
async def test_pending_is_cleaned_up_after_resolve(runtime):
    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r1"), emit, owner="A"))
    await asyncio.sleep(0.05)
    runtime.resolve_confirm("r1", True)
    await task
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_task_registry_lifecycle(runtime):
    async def forever():
        await asyncio.sleep(30)

    task = asyncio.create_task(forever())
    running = runtime.register_task("session-1", task)
    assert running.id in runtime.tasks
    assert runtime.cancel_session_tasks("session-1") == 1
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()

    runtime.unregister_task(running.id)
    assert runtime.tasks == {}


@pytest.mark.asyncio
async def test_cancel_unknown_task_returns_false(runtime):
    assert runtime.cancel_task("nope") is False
