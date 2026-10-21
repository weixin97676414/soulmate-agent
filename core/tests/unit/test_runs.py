





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

    run_id = await store.start(kind="task", ref_id="t1", session_id="s1")
    
    assert await store.get(run_id) is not None
    assert await store.list_pending() == []

    await store.finish(run_id)

    assert await store.get(run_id) is None


@pytest.mark.asyncio
async def test_interrupted_run_keeps_the_scene(store):

    run_id = await store.start(kind="task", ref_id="t1", session_id="s1")
    await store.progress(run_id, step=3, last_action="excel_write")
    await store.interrupt(
        run_id, status="failed", step=3, last_action="excel_write", error="模型挂了"
    )

    pending = await store.list_pending()

    assert len(pending) == 1
    run = pending[0]
    
    assert (run.kind, run.ref_id, run.session_id) == ("task", "t1", "s1")
    assert run.status == "failed"
    assert run.step == 3
    assert run.last_action == "excel_write"
    assert "模型挂了" in run.error


@pytest.mark.asyncio
async def test_running_rows_are_not_offered_for_resume(store):

    await store.start(kind="task", ref_id="t1")

    assert await store.list_pending() == []


@pytest.mark.asyncio
async def test_clear_running_drops_stale_rows(store):

    await store.start(kind="task", ref_id="t1")

    assert await store.clear_running() == 1
    assert await store.list_pending() == []


@pytest.mark.asyncio
async def test_attach_session_fills_the_missing_link(store):

    run_id = await store.start(kind="task", ref_id="t1")

    await store.attach_session(run_id, "s9")

    run = await store.get(run_id)
    assert run is not None and run.session_id == "s9"


@pytest.mark.asyncio
async def test_without_database_it_quietly_noops(tmp_path):

    store = RunStore(Database(tmp_path / "never.db"))

    assert await store.start(kind="task") == ""
    await store.progress("", step=1)  
    await store.finish("")
    assert await store.list_pending() == []
