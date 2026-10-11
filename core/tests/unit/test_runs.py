"""未完成运行的进度（断点续跑）。

这组守的是几件"用户点一次就再也不用管"的事：进度真的落盘、正常跑完不留痕、
失败/叫停留下可续跑的现场、上次被强杀的残留不会永远挂在那儿。
"""

from __future__ import annotations

import pytest

from my_agent.storage.db import Database
from my_agent.storage.runs import RunStore


@pytest.fixture
async def store(tmp_path):
    db = Database(tmp_path / "runs.db")
    await db.connect()
    yield RunStore(db)
    await db.close()


@pytest.mark.asyncio
async def test_finished_run_leaves_nothing(store):
    """正常跑完就把进度删掉：界面上不该永远挂着一个「继续」。"""
    run_id = await store.start(kind="task", ref_id="t1", session_id="s1")
    # 刚起的时候是 running，**不出现在「继续」列表里**（点它会起第二个并发执行）
    assert await store.get(run_id) is not None
    assert await store.list_pending() == []

    await store.finish(run_id)

    assert await store.get(run_id) is None


@pytest.mark.asyncio
async def test_interrupted_run_keeps_the_scene(store):
    """失败/叫停要留下"接着哪个会话、做到第几步、最后在做什么"。"""
    run_id = await store.start(kind="task", ref_id="t1", session_id="s1")
    await store.progress(run_id, step=3, last_action="excel_write")
    await store.interrupt(
        run_id, status="failed", step=3, last_action="excel_write", error="模型挂了"
    )

    pending = await store.list_pending()

    assert len(pending) == 1
    run = pending[0]
    # 会话 id 是"接着跑"的关键：没有它就只能从零再来一遍
    assert (run.kind, run.ref_id, run.session_id) == ("task", "t1", "s1")
    assert run.status == "failed"
    assert run.step == 3
    assert run.last_action == "excel_write"
    assert "模型挂了" in run.error


@pytest.mark.asyncio
async def test_running_rows_are_not_offered_for_resume(store):
    """还在跑的不出现在「继续」列表里 —— 否则用户会点出第二个并发执行。"""
    await store.start(kind="task", ref_id="t1")

    assert await store.list_pending() == []


@pytest.mark.asyncio
async def test_clear_running_drops_stale_rows(store):
    """上次被强杀留下的"还在跑"要清掉：它们没有可续跑的现场。"""
    await store.start(kind="task", ref_id="t1")

    assert await store.clear_running() == 1
    assert await store.list_pending() == []


@pytest.mark.asyncio
async def test_attach_session_fills_the_missing_link(store):
    """会话是执行中才建出来的，所以要能后补（补不上就没法接着跑）。"""
    run_id = await store.start(kind="task", ref_id="t1")

    await store.attach_session(run_id, "s9")

    run = await store.get(run_id)
    assert run is not None and run.session_id == "s9"


@pytest.mark.asyncio
async def test_without_database_it_quietly_noops(tmp_path):
    """数据库不可用（纯内存降级）时记进度不能把对话搞崩。"""
    store = RunStore(Database(tmp_path / "never.db"))

    assert await store.start(kind="task") == ""
    await store.progress("", step=1)  # 不该抛
    await store.finish("")
    assert await store.list_pending() == []
