






from __future__ import annotations

import asyncio

import pytest

from my_agent.config.paths import AppPaths
from my_agent.security.confirm import ConfirmRequest
from my_agent.server.runtime import AppRuntime


@pytest.fixture
def runtime(tmp_path) -> AppRuntime:
    
    
    
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






    
    runtime.config.settings.security.confirm_timeout_seconds = 0.2

    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r1"), emit, owner="A"))
    
    await asyncio.sleep(0.6)
    assert not task.done(), "确认不该自己结束 —— 只有收到响应或被打断才能收尾"
    assert "r1" in runtime.pending_confirms, "挂起表里要留着它，否则没人能再回传结果"

    
    assert runtime.resolve_confirm("r1", True) is True
    assert await task is True
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_任务被打断时确认作废(runtime):





    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r2"), emit, owner="A"))
    await asyncio.sleep(0)  
    assert runtime.reject_pending(owner="A") == 1
    assert await task is False
    assert runtime.pending_confirms == {}


@pytest.mark.asyncio
async def test_别的会话被打断时不影响我的确认(runtime):


    async def emit(_request):
        return None

    task = asyncio.create_task(runtime.request_confirm(make_request("r3"), emit, owner="A"))
    await asyncio.sleep(0)
    
    assert runtime.reject_pending(owner="B") == 0
    assert not task.done()
    assert runtime.resolve_confirm("r3", False) is True
    assert await task is False


@pytest.mark.asyncio
async def test_reject_pending_is_scoped_to_owner(runtime):

    emitted: list[str] = []

    async def emit(request: ConfirmRequest):
        emitted.append(request.request_id)

    task_a = asyncio.create_task(runtime.request_confirm(make_request("a1"), emit, owner="A"))
    task_b = asyncio.create_task(runtime.request_confirm(make_request("b1"), emit, owner="B"))
    await asyncio.sleep(0.05)

    assert set(runtime.pending_confirms) == {"a1", "b1"}

    runtime.reject_pending("A")
    assert await task_a is False
    
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
