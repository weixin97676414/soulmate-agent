





from __future__ import annotations

import pytest

from my_agent.config.paths import AppPaths
from my_agent.security.audit import AuditEntry
from my_agent.server.runtime import AppRuntime


@pytest.fixture
def paths(tmp_path) -> AppPaths:
    return AppPaths(tmp_path / "AgentDesktop").ensure()


async def build_runtime(paths: AppPaths) -> AppRuntime:
    runtime = AppRuntime(paths)
    await runtime.initialize()
    return runtime


@pytest.mark.asyncio
async def test_session_and_messages_survive_restart(paths):
    first = await build_runtime(paths)
    assert first.db_ready is True

    session = await first.sessions.create(title="季度销售分析")
    session.memory.add_user("帮我分析一下这个季度的销售数据")
    session.memory.add_assistant("好的，我先读取表格。")
    session.touch()
    await first.persist_session(session)
    session_id = session.id
    await first.shutdown()

    
    second = await build_runtime(paths)
    listed = second.sessions.list()
    assert len(listed) == 1
    assert listed[0]["id"] == session_id
    assert listed[0]["title"] == "季度销售分析"
    assert listed[0]["message_count"] == 2

    restored = await second.sessions.get(session_id)
    contents = [m.content for m in restored.memory.messages]
    assert contents == ["帮我分析一下这个季度的销售数据", "好的，我先读取表格。"]
    await second.shutdown()


@pytest.mark.asyncio
async def test_incremental_append_across_turns_survives_restart(paths):






    first = await build_runtime(paths)
    session = await first.sessions.create(title="长会话")
    session.memory.add_user("第一轮提问")
    session.memory.add_assistant("第一轮回答")
    await first.persist_session(session)

    
    session.memory.add_user("第二轮提问")
    session.memory.add_assistant("第二轮回答")
    session.touch()
    await first.persist_session(session)

    
    session.memory.add_user("第三轮提问")
    session.touch()
    await first.persist_session(session)
    session_id = session.id
    await first.shutdown()

    second = await build_runtime(paths)
    restored = await second.sessions.get(session_id)
    assert [m.content for m in restored.memory.messages] == [
        "第一轮提问",
        "第一轮回答",
        "第二轮提问",
        "第二轮回答",
        "第三轮提问",
    ]
    await second.shutdown()


@pytest.mark.asyncio
async def test_clear_history_really_deletes_on_disk(paths):





    first = await build_runtime(paths)
    session = await first.sessions.create(title="清空")
    session.memory.add_user("要被清掉的")
    session.memory.add_assistant("也要清")
    await first.persist_session(session)

    await first.sessions.clear_history(session.id)
    session_id = session.id
    await first.shutdown()

    second = await build_runtime(paths)
    restored = await second.sessions.get(session_id)
    
    assert [m.content for m in restored.memory.messages] == []
    assert restored.history() == []
    await second.shutdown()


@pytest.mark.asyncio
async def test_messages_are_loaded_lazily(paths):

    first = await build_runtime(paths)
    session = await first.sessions.create(title="会话 A")
    session.memory.add_user("内容")
    session.memory.add_assistant("回复")
    await first.persist_session(session)
    await first.shutdown()

    second = await build_runtime(paths)
    
    cached = second.sessions._sessions[session.id]  
    assert len(cached.memory) == 0

    
    loaded = await second.sessions.get(session.id)
    assert len(loaded.memory) == 2
    await second.shutdown()


@pytest.mark.asyncio
async def test_tool_call_history_survives_restart(paths):
    from my_agent.llm.base import ToolCall

    first = await build_runtime(paths)
    session = await first.sessions.create(title="工具调用")
    session.memory.add_user("算 1+2")
    session.memory.add_assistant(
        "",
        tool_calls=[
            ToolCall(id="c1", name="calc", arguments={"expression": "1+2"}, raw_arguments='{"expression": "1+2"}')
        ],
    )
    session.memory.add_tool("c1", "calc", '{"result": 3}')
    session.memory.add_assistant("结果是 3")
    await first.persist_session(session)
    session_id = session.id
    await first.shutdown()

    second = await build_runtime(paths)
    restored = await second.sessions.get(session_id)
    roles = [m.role for m in restored.memory.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]
    restored_calls = restored.memory.messages[1].tool_calls
    assert restored_calls and restored_calls[0].name == "calc"
    
    assert restored.memory.messages[2].tool_call_id == "c1"
    
    
    
    
    
    
    
    
    history = restored.history()
    assert [item["role"] for item in history] == ["user", "assistant", "assistant"]
    assert history[1]["tool_calls"][0]["name"] == "calc"
    assert history[2]["content"] == "结果是 3"
    await second.shutdown()


@pytest.mark.asyncio
async def test_session_metadata_updates_persist(paths):
    first = await build_runtime(paths)
    session = await first.sessions.create(title="旧标题")
    await first.sessions.rename(session.id, "新标题")
    await first.sessions.update_meta(session.id, model_id="deepseek-chat")
    session_id = session.id
    await first.shutdown()

    second = await build_runtime(paths)
    restored = await second.sessions.get(session_id)
    assert restored.title == "新标题"
    assert restored.model_id == "deepseek-chat"
    await second.shutdown()


@pytest.mark.asyncio
async def test_deleted_session_stays_deleted(paths):
    first = await build_runtime(paths)
    session = await first.sessions.create(title="待删除")
    session.memory.add_user("内容")
    await first.persist_session(session)
    session_id = session.id

    assert await first.sessions.delete(session_id) is True
    await first.shutdown()

    second = await build_runtime(paths)
    assert second.sessions.list() == []
    with pytest.raises(Exception):  
        await second.sessions.get(session_id)
    await second.shutdown()


@pytest.mark.asyncio
async def test_changing_system_prompt_resets_history(paths):
    first = await build_runtime(paths)
    session = await first.sessions.create(title="会话")
    session.memory.add_user("旧人设下的对话")
    session.memory.add_assistant("回复")
    await first.persist_session(session)

    updated = await first.sessions.update_meta(session.id, system_prompt="你现在是法律顾问")
    
    assert updated.history() == []
    await first.shutdown()


@pytest.mark.asyncio
async def test_audit_entries_survive_restart(paths):
    first = await build_runtime(paths)
    await first.audit.record(
        AuditEntry(skill_name="calc", status="ok", session_id="s1", params={"expression": "1+2"})
    )
    await first.audit.record(
        AuditEntry(skill_name="write_file", status="denied", permission_level="confirm")
    )
    await first.shutdown()

    second = await build_runtime(paths)
    stats = await second.audit_repo.stats()
    assert stats["total"] == 2
    assert stats["by_status"] == {"ok": 1, "denied": 1}
    entries = await second.audit_repo.query(skill_name="calc")
    assert entries[0]["params"] == {"expression": "1+2"}
    await second.shutdown()


@pytest.mark.asyncio
async def test_workspace_files_survive_restart(paths):
    first = await build_runtime(paths)
    record = await first.workspace.save_upload(filename="报表.xlsx", content=b"data")
    file_id = record.id
    await first.shutdown()

    second = await build_runtime(paths)
    listed = await second.workspace.list_files()
    assert [item.id for item in listed] == [file_id]
    assert listed[0].original_name == "报表.xlsx"
    assert second.workspace.resolve(file_id, "upload").read_bytes() == b"data"
    await second.shutdown()


@pytest.mark.asyncio
async def test_degrades_to_memory_mode_when_db_unavailable(paths, monkeypatch):

    from my_agent.storage.db import Database

    async def broken_connect(self) -> None:
        raise RuntimeError("模拟磁盘故障")

    monkeypatch.setattr(Database, "connect", broken_connect)

    runtime = await build_runtime(paths)
    assert runtime.db_ready is False
    assert runtime.sessions.persistent is False

    
    session = await runtime.sessions.create(title="内存会话")
    session.memory.add_user("你好")
    await runtime.persist_session(session)  
    assert len(runtime.sessions.list()) == 1
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_memory_only_runtime_matches_persistent_api(paths):

    runtime = await build_runtime(paths)
    session = await runtime.sessions.create(title="A")
    await runtime.sessions.rename(session.id, "B")
    assert (await runtime.sessions.get(session.id)).title == "B"
    assert await runtime.sessions.delete(session.id) is True
    assert runtime.sessions.list() == []
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_audit_retention_cleanup_on_startup(paths):

    import time

    first = await build_runtime(paths)
    await first.audit_repo.record(
        AuditEntry(skill_name="ancient", status="ok", ts=time.time() - 200 * 86400)
    )
    await first.audit_repo.record(AuditEntry(skill_name="recent", status="ok"))
    await first.shutdown()

    second = await build_runtime(paths)
    stats = await second.audit_repo.stats()
    assert stats["total"] == 1
    assert stats["top_skills"][0]["skill_name"] == "recent"
    await second.shutdown()
