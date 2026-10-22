







from __future__ import annotations

import pytest

from my_agent.config.paths import AppPaths
from my_agent.llm.base import Message, ToolCall
from my_agent.security.audit import AuditEntry
from my_agent.storage.audit import AuditRepository
from my_agent.storage.db import Database, DatabaseError
from my_agent.storage.files import WorkspaceError, WorkspaceStore
from my_agent.storage.sessions import SessionRecord, SessionRepository


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def repo(db):
    return SessionRepository(db)





@pytest.mark.asyncio
async def test_connect_creates_schema(tmp_path):
    database = Database(tmp_path / "sub" / "deep" / "test.db")
    await database.connect()
    assert database.connected
    tables = await database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row["name"] for row in tables}
    assert {"sessions", "messages", "audit_log", "files"} <= names

    version = await database.fetch_one("PRAGMA user_version")
    assert version["user_version"] >= 1
    await database.close()

    
    again = Database(tmp_path / "sub" / "deep" / "test.db")
    await again.connect()
    assert again.connected
    await again.close()


@pytest.mark.asyncio
async def test_operations_before_connect_raise(tmp_path):
    database = Database(tmp_path / "never.db")
    with pytest.raises(DatabaseError):
        await database.fetch_all("SELECT 1")


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_error(db):
    
    
    insert = (
        "INSERT INTO sessions (id, title, model_id, system_prompt, message_count, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    await db.execute(insert, ("s1", "t", "m", "", 0, 1.0, 1.0))
    with pytest.raises(DatabaseError):
        await db.transaction(
            [
                ("UPDATE sessions SET title = 'changed' WHERE id = 's1'", ()),
                (insert, ("s1", "dup", "m", "", 0, 1.0, 1.0)),  
            ]
        )
    row = await db.fetch_one("SELECT title FROM sessions WHERE id = 's1'")
    
    assert row["title"] == "t"


def test_schema_version_matches_the_migrations():









    from my_agent.storage.db import MIGRATIONS, SCHEMA_VERSION

    assert SCHEMA_VERSION == max(MIGRATIONS), "SCHEMA_VERSION 与迁移表的最大版本号不一致"
    assert sorted(MIGRATIONS) == list(range(1, SCHEMA_VERSION + 1)), (
        f"迁移必须从 1 连续编号，实际是 {sorted(MIGRATIONS)}"
    )


def test_migration_scripts_have_no_semicolon_inside_literals():










    import re as _re

    from my_agent.storage.db import MIGRATIONS

    literal = _re.compile(r"'([^']*)'")
    offenders: list[str] = []
    for version, script in MIGRATIONS.items():
        
        body = "\n".join(
            line for line in script.splitlines() if not line.strip().startswith("--")
        )
        for found in literal.finditer(body):
            if ";" in found.group(1):
                offenders.append(f"v{version}: {found.group(1)!r}")
    assert offenders == [], (
        f"迁移脚本的字面量里含分号，_split_statements 会把语句拆坏：{offenders}"
    )





@pytest.mark.asyncio
async def test_session_round_trip(repo):
    record = SessionRecord(id="s1", title="季度分析", model_id="deepseek-chat", message_count=2)
    await repo.save_session(
        record,
        [
            Message(role="system", content="你是助手"),
            Message(role="user", content="帮我算一下"),
            Message(role="assistant", content="好的"),
        ],
    )

    loaded = await repo.get_session("s1")
    assert loaded.title == "季度分析"
    assert loaded.model_id == "deepseek-chat"
    assert loaded.message_count == 2

    messages = await repo.load_messages("s1")
    assert [m.role for m in messages] == ["system", "user", "assistant"]
    assert messages[0].content == "你是助手"


@pytest.mark.asyncio
async def test_tool_calls_survive_round_trip(repo):

    calls = [
        ToolCall(
            id="call_1",
            name="calc",
            arguments={"expression": "1+2"},
            raw_arguments='{"expression": "1+2"}',
        )
    ]
    await repo.save_session(
        SessionRecord(id="s1"),
        [
            Message(role="user", content="算一下"),
            Message(role="assistant", content="", tool_calls=calls),
            Message(role="tool", content='{"result": 3}', tool_call_id="call_1", name="calc"),
        ],
    )

    messages = await repo.load_messages("s1")
    assistant = messages[1]
    assert assistant.tool_calls is not None
    assert assistant.tool_calls[0].name == "calc"
    assert assistant.tool_calls[0].arguments == {"expression": "1+2"}
    assert assistant.tool_calls[0].raw_arguments == '{"expression": "1+2"}'
    assert messages[2].tool_call_id == "call_1"
    assert messages[2].name == "calc"


@pytest.mark.asyncio
async def test_replace_messages_is_idempotent(repo):
    record = SessionRecord(id="s1")
    await repo.save_session(record, [Message(role="user", content="第一条")])
    await repo.save_session(record, [Message(role="user", content="第二条")])

    messages = await repo.load_messages("s1")
    assert len(messages) == 1
    assert messages[0].content == "第二条"


@pytest.mark.asyncio
async def test_append_mode_only_writes_the_new_tail(repo, db):





    record = SessionRecord(id="s1")
    first = Message(role="system", content="人设")
    await repo.save_session(record, [first], mode="append")

    await repo.save_session(
        record,
        [first, Message(role="user", content="问题"), Message(role="assistant", content="回答")],
        mode="append",
    )

    loaded = await repo.load_messages("s1")
    assert [m.content for m in loaded] == ["人设", "问题", "回答"]
    
    rows = await db.fetch_all("SELECT seq FROM messages WHERE session_id = 's1' ORDER BY seq")
    assert [int(row["seq"]) for row in rows] == [0, 1, 2]


@pytest.mark.asyncio
async def test_append_mode_falls_back_when_history_shrank(repo):





    record = SessionRecord(id="s1")
    three = [
        Message(role="user", content="一"),
        Message(role="assistant", content="二"),
        Message(role="user", content="三"),
    ]
    await repo.save_session(record, three, mode="append")

    
    await repo.save_session(record, three[:2], mode="append")

    loaded = await repo.load_messages("s1")
    assert [m.content for m in loaded] == ["一", "二"]


@pytest.mark.asyncio
async def test_append_mode_falls_back_when_last_message_was_replaced(repo):





    record = SessionRecord(id="s1")
    await repo.save_session(
        record, [Message(role="user", content="问"), Message(role="assistant", content="旧答案")],
        mode="append",
    )

    await repo.save_session(
        record, [Message(role="user", content="问"), Message(role="assistant", content="新答案")],
        mode="append",
    )

    loaded = await repo.load_messages("s1")
    assert loaded[-1].content == "新答案"


@pytest.mark.asyncio
async def test_append_mode_falls_back_when_prefix_shifted(repo):

    record = SessionRecord(id="s1")
    await repo.save_session(
        record,
        [Message(role="user", content="问"), Message(role="assistant", content="答")],
        mode="append",
    )

    await repo.save_session(
        record,
        [
            Message(role="system", content="新人设"),
            Message(role="user", content="问"),
            Message(role="assistant", content="答"),
        ],
        mode="append",
    )

    loaded = await repo.load_messages("s1")
    assert [m.role for m in loaded] == ["system", "user", "assistant"]
    assert loaded[0].content == "新人设"


@pytest.mark.asyncio
async def test_default_mode_is_still_replace(repo):





    record = SessionRecord(id="s1")
    await repo.save_session(
        record,
        [Message(role="user", content="一"), Message(role="user", content="二")],
    )
    await repo.save_session(record, [Message(role="user", content="只剩我")])

    loaded = await repo.load_messages("s1")
    assert [m.content for m in loaded] == ["只剩我"]


@pytest.mark.asyncio
async def test_save_without_messages_keeps_existing(repo):

    record = SessionRecord(id="s1", title="旧标题")
    await repo.save_session(record, [Message(role="user", content="内容")])

    await repo.save_session(SessionRecord(id="s1", title="新标题"), None)

    assert (await repo.get_session("s1")).title == "新标题"
    assert len(await repo.load_messages("s1")) == 1


@pytest.mark.asyncio
async def test_delete_session_removes_messages(repo):
    await repo.save_session(SessionRecord(id="s1"), [Message(role="user", content="x")])
    assert await repo.delete_session("s1") is True
    assert await repo.get_session("s1") is None
    assert await repo.load_messages("s1") == []
    assert await repo.delete_session("s1") is False


@pytest.mark.asyncio
async def test_clear_messages(repo):
    await repo.save_session(SessionRecord(id="s1"), [Message(role="user", content="x")])
    await repo.clear_messages("s1")
    assert await repo.load_messages("s1") == []
    assert (await repo.get_session("s1")).message_count == 0


@pytest.mark.asyncio
async def test_list_sessions_sorted_by_updated(repo):
    await repo.save_session(SessionRecord(id="old", updated_at=100.0))
    await repo.save_session(SessionRecord(id="new", updated_at=200.0))
    listed = await repo.list_sessions()
    assert [item.id for item in listed] == ["new", "old"]


@pytest.mark.asyncio
async def test_enabled_skills_round_trip(repo):
    await repo.save_session(SessionRecord(id="s1", enabled_skills=["calc", "system_time"]))
    loaded = await repo.get_session("s1")
    assert loaded.enabled_skills == ["calc", "system_time"]


@pytest.mark.asyncio
async def test_corrupted_tool_calls_do_not_crash(db, repo):

    await repo.save_session(SessionRecord(id="s1"), [Message(role="user", content="x")])
    await db.execute("UPDATE messages SET tool_calls = '{坏掉的JSON' WHERE session_id = 's1'")
    messages = await repo.load_messages("s1")
    assert len(messages) == 1
    assert messages[0].tool_calls is None





@pytest.fixture
async def audit(db):
    return AuditRepository(db)


@pytest.mark.asyncio
async def test_audit_redacts_sensitive_params(audit):
    await audit.record(
        AuditEntry(
            skill_name="send_email",
            status="ok",
            permission_level="confirm",
            session_id="s1",
            params={"to": "13812345678", "api_key": "sk-abcdefghijklmn"},
            duration_ms=12.5,
        )
    )
    entries = await audit.query()
    assert len(entries) == 1
    params = entries[0]["params"]
    assert "13812345678" not in str(params)
    assert "sk-abcdefghijklmn" not in str(params)
    assert entries[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_audit_filters_and_stats(audit):
    for index, status in enumerate(["ok", "ok", "denied", "error"]):
        await audit.record(
            AuditEntry(skill_name="calc" if index < 2 else "write_file", status=status)
        )

    assert len(await audit.query(skill_name="calc")) == 2
    assert len(await audit.query(status="denied")) == 1

    stats = await audit.stats()
    assert stats["total"] == 4
    assert stats["by_status"] == {"ok": 2, "denied": 1, "error": 1}
    
    assert {item["skill_name"] for item in stats["top_skills"]} == {"calc", "write_file"}
    assert all(item["count"] == 2 for item in stats["top_skills"])


@pytest.mark.asyncio
async def test_audit_purge_and_clear(audit):
    import time

    await audit.record(AuditEntry(skill_name="a", status="ok", ts=time.time() - 400 * 86400))
    await audit.record(AuditEntry(skill_name="b", status="ok"))

    assert await audit.purge_older_than(90) == 1
    assert (await audit.stats())["total"] == 1
    assert await audit.clear() == 1





@pytest.fixture
def workspace(tmp_path):
    store = WorkspaceStore(
        workspace_dir=tmp_path / "workspace",
        artifacts_dir=tmp_path / "artifacts",
    )
    store.ensure_dirs()
    return store


@pytest.mark.asyncio
async def test_upload_and_download(workspace):
    record = await workspace.save_upload(filename="销售数据.xlsx", content=b"hello")
    assert record.original_name == "销售数据.xlsx"
    assert record.size == 5
    
    assert record.id != "销售数据.xlsx"
    assert record.id.endswith(".xlsx")

    path = workspace.resolve(record.id, "upload")
    assert path.read_bytes() == b"hello"

    listed = await workspace.list_files()
    assert [item.id for item in listed] == [record.id]


@pytest.mark.asyncio
async def test_upload_blocks_dangerous_suffix(workspace):
    for name in ["virus.exe", "script.bat", "run.ps1", "lib.dll", "x.msi"]:
        with pytest.raises(WorkspaceError) as exc:
            await workspace.save_upload(filename=name, content=b"x")
        assert "安全" in str(exc.value)


@pytest.mark.asyncio
async def test_upload_rejects_oversize(workspace):
    from my_agent.storage.files import MAX_UPLOAD_BYTES

    with pytest.raises(WorkspaceError) as exc:
        await workspace.save_upload(filename="big.bin", content=b"0" * (MAX_UPLOAD_BYTES + 1))
    assert "过大" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_rejects_path_traversal(workspace):





    evil_ids = [
        "../secret.txt",
        "..\\secret.txt",
        "a/b.txt",
        "sub/../x",
        ".hidden",  
        "trailing.",  
        "trailing ",
        "bad:name.txt",  
        "bad?name.txt",
        "bad*name.txt",
        "C:absolute.txt",
        "",
    ]
    for evil in evil_ids:
        with pytest.raises(WorkspaceError):
            workspace.resolve(evil, "upload")


@pytest.mark.asyncio
async def test_resolve_accepts_non_ascii_names(workspace):









    for name in ["业务架构图.svg", "销售 报表.xlsx", "报告（终版）.docx", "a-b_c.v2.txt"]:
        target = workspace.artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        assert workspace.resolve(name, "artifact") == target.resolve()


@pytest.mark.asyncio
async def test_register_artifact_rejects_unusable_name(workspace):

    workspace.ensure_dirs()
    (workspace.artifacts_dir / ".hidden.svg").write_text("<svg/>", encoding="utf-8")
    with pytest.raises(WorkspaceError) as exc:
        await workspace.register_artifact(workspace.artifacts_dir / ".hidden.svg")
    assert "不可用" in str(exc.value)


@pytest.mark.asyncio
async def test_resolve_rejects_missing(workspace):
    with pytest.raises(WorkspaceError) as exc:
        workspace.resolve("notexist.txt", "upload")
    assert "不存在" in str(exc.value)


@pytest.mark.asyncio
async def test_upload_strips_directory_from_filename(workspace):

    record = await workspace.save_upload(filename="C:/tmp/evil/../../note.txt", content=b"x")
    assert "/" not in record.original_name
    assert "\\" not in record.original_name


@pytest.mark.asyncio
async def test_delete_file(workspace):
    record = await workspace.save_upload(filename="a.txt", content=b"x")
    assert await workspace.delete(record.id, kind="upload") is True
    assert await workspace.delete(record.id, kind="upload") is False
    assert await workspace.list_files() == []


@pytest.mark.asyncio
async def test_artifact_and_upload_are_separate(workspace):
    await workspace.save_upload(filename="in.txt", content=b"x")
    artifact = workspace.artifacts_dir / "report.md"
    artifact.write_text("# 报告", encoding="utf-8")
    await workspace.register_artifact(artifact, note="周报")

    assert len(await workspace.list_files(kind="upload")) == 1
    assert len(await workspace.list_files(kind="artifact")) == 1
    stats = await workspace.stats()
    assert stats["uploads"] == 1
    assert stats["artifacts"] == 1


@pytest.mark.asyncio
async def test_register_missing_artifact_raises(workspace):
    with pytest.raises(WorkspaceError):
        await workspace.register_artifact(workspace.artifacts_dir / "ghost.md")


@pytest.mark.asyncio
async def test_workspace_scan_without_database(tmp_path):

    store = WorkspaceStore(
        workspace_dir=tmp_path / "ws", artifacts_dir=tmp_path / "ar", db=None
    )
    await store.save_upload(filename="a.txt", content=b"123")
    listed = await store.list_files()
    assert len(listed) == 1
    assert listed[0].size == 3
    assert (await store.stats())["total_bytes"] == 3


def test_paths_layout(tmp_path):
    paths = AppPaths(tmp_path / "root").ensure()
    assert paths.settings_file.parent == paths.config_dir
    assert paths.db_file.parent == paths.data_dir
    assert paths.workspace_dir.is_dir()
    assert paths.artifacts_dir.is_dir()





@pytest.mark.asyncio
async def test_message_timestamps_survive_repeated_saves(repo):






    record = SessionRecord(id="s1", title="时间")
    older = Message(role="user", content="昨天说的", created_at=1_700_000_000.0)
    newer = Message(role="assistant", content="刚才说的", created_at=1_700_000_600.0)

    await repo.save_session(record, [older])
    
    await repo.save_session(record, [older, newer])

    loaded = await repo.load_messages("s1")
    assert [m.created_at for m in loaded] == [1_700_000_000.0, 1_700_000_600.0]


@pytest.mark.asyncio
async def test_legacy_rows_are_read_back_as_unknown_time(repo, db):






    await repo.save_session(SessionRecord(id="s2", title="老会话"))
    
    await db.execute(
        "INSERT INTO messages (session_id, seq, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("s2", 0, "user", "旧消息", 1_600_000_000.0),
    )

    loaded = await repo.load_messages("s2")

    assert loaded[0].content == "旧消息"
    assert loaded[0].created_at is None


@pytest.mark.asyncio
async def test_message_without_a_stamp_is_marked_untrusted(repo):

    await repo.save_session(SessionRecord(id="s3"), [Message(role="system", content="人格")])

    loaded = await repo.load_messages("s3")

    assert loaded[0].content == "人格"
    assert loaded[0].created_at is None
