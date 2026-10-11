"""存储层测试：SQLite 仓储与工作区文件。

重点覆盖三类容易出错的地方：
1. 消息（尤其是带 tool_calls 的）写入后能否原样读回；
2. 工作区的路径安全（文件名不可信、id 不可越界）；
3. 审计写入前是否真的做了脱敏。
"""

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


# --------------------------------------------------------------------------- #
# 数据库与迁移
# --------------------------------------------------------------------------- #
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

    # 二次连接应幂等（不应重复建表或报错）
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
    # 显式列出列名：用 `INSERT INTO sessions VALUES (...)` 这种写法会在
    # 每次加列时失效，报一个跟本用例意图（事务回滚）毫无关系的错
    insert = (
        "INSERT INTO sessions (id, title, model_id, system_prompt, message_count, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    await db.execute(insert, ("s1", "t", "m", "", 0, 1.0, 1.0))
    with pytest.raises(DatabaseError):
        await db.transaction(
            [
                ("UPDATE sessions SET title = 'changed' WHERE id = 's1'", ()),
                (insert, ("s1", "dup", "m", "", 0, 1.0, 1.0)),  # 主键冲突
            ]
        )
    row = await db.fetch_one("SELECT title FROM sessions WHERE id = 's1'")
    # 前半段必须被回滚
    assert row["title"] == "t"


def test_schema_version_matches_the_migrations():
    """`SCHEMA_VERSION` 必须与迁移表**严格对齐**（第 91 批，L-19）。

    两个都容易漏、且漏了**不报错**：

    * 加了迁移却忘了抬 `SCHEMA_VERSION` ⇒ `_migrate` 根本不看那条脚本，
      新列永远不会被建出来，而库看起来完全正常 —— 直到有人用到它；
    * 迁移编号出现空号（比如只有 1..12 与 14）⇒ 升级时按序执行会**直接跳过 13**，
      同样没有任何报错。
    """
    from my_agent.storage.db import MIGRATIONS, SCHEMA_VERSION

    assert SCHEMA_VERSION == max(MIGRATIONS), "SCHEMA_VERSION 与迁移表的最大版本号不一致"
    assert sorted(MIGRATIONS) == list(range(1, SCHEMA_VERSION + 1)), (
        f"迁移必须从 1 连续编号，实际是 {sorted(MIGRATIONS)}"
    )


def test_migration_scripts_have_no_semicolon_inside_literals():
    """迁移脚本里**不许**出现含分号的字符串字面量（第 91 批，L-19②）。

    `db._split_statements` 是按 `;` **硬拆**的（刻意不用 `executescript`：
    那个会在执行前隐式提交，于是「DDL 与 user_version」没法作为一个事务提交）。
    这个做法成立的前提是"脚本里没有含分号的字面量" —— 而这条前提以前只写在
    docstring 里，**没有任何东西守着**。

    哪天有人加一句 `INSERT INTO x VALUES ('a;b')`，整条迁移会被拆成两半，
    报出来的还是个跟本意毫无关系的语法错 —— 而且是在**用户机器上升级时**才炸。
    """
    import re as _re

    from my_agent.storage.db import MIGRATIONS

    literal = _re.compile(r"'([^']*)'")
    offenders: list[str] = []
    for version, script in MIGRATIONS.items():
        # 先去掉整行注释：注释里写引号和分号不该算进这条不变量
        body = "\n".join(
            line for line in script.splitlines() if not line.strip().startswith("--")
        )
        for found in literal.finditer(body):
            if ";" in found.group(1):
                offenders.append(f"v{version}: {found.group(1)!r}")
    assert offenders == [], (
        f"迁移脚本的字面量里含分号，_split_statements 会把语句拆坏：{offenders}"
    )


# --------------------------------------------------------------------------- #
# 会话仓储
# --------------------------------------------------------------------------- #
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
    """tool_calls 是 JSON 序列化的，最容易在转换中丢字段。"""
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
    """追加模式只写尾巴，且 ``seq`` 从已存的那一段续上（第 87 批 B 组，M-04）。

    这条钉的是**写放大**：以前每轮都 DELETE 全部 + INSERT 全部（O(n²)），
    长会话越聊越卡。追加之后只应写入新增的那几条。
    """
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
    # seq 必须是 0/1/2 连续的 —— 续写时算错起点会让 order by seq 读出乱序
    rows = await db.fetch_all("SELECT seq FROM messages WHERE session_id = 's1' ORDER BY seq")
    assert [int(row["seq"]) for row in rows] == [0, 1, 2]


@pytest.mark.asyncio
async def test_append_mode_falls_back_when_history_shrank(repo):
    """内存比库里**少**（回滚重试 / 清空）时必须退回整体替换。

    否则被删掉的消息会**留在库里**，重启后用户看到已经删掉的对话又回来了 ——
    这比"写慢一点"严重得多。
    """
    record = SessionRecord(id="s1")
    three = [
        Message(role="user", content="一"),
        Message(role="assistant", content="二"),
        Message(role="user", content="三"),
    ]
    await repo.save_session(record, three, mode="append")

    # 模拟 `pop_last_assistant()`：内存里只剩前两条
    await repo.save_session(record, three[:2], mode="append")

    loaded = await repo.load_messages("s1")
    assert [m.content for m in loaded] == ["一", "二"]


@pytest.mark.asyncio
async def test_append_mode_falls_back_when_last_message_was_replaced(repo):
    """条数不变、**最后一条被换掉**时也必须退回整体替换。

    `pop_last_assistant()` 回滚之后引擎会补一条新 assistant 消息，长度**有可能恰好相等**
    —— 只比长度的话就会把旧内容留在库里（用户重启后看到的是上一版回答）。
    """
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
    """前面被插进一条（改人设时的 ``insert(0, ...)``）⇒ ``seq`` 整体挪位，必须整体替换。"""
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
    """⚠️ 默认必须是 ``replace``：调用方漏传 mode 时要落在**安全的那一侧**。

    ``clear_history()`` / 改系统提示词都靠整体替换删旧行，默认改成追加会让它们
    变成"删了但没删掉"。
    """
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
    """只改标题不应该把消息清掉。"""
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
    """手工改坏数据库不应让整个会话打不开。"""
    await repo.save_session(SessionRecord(id="s1"), [Message(role="user", content="x")])
    await db.execute("UPDATE messages SET tool_calls = '{坏掉的JSON' WHERE session_id = 's1'")
    messages = await repo.load_messages("s1")
    assert len(messages) == 1
    assert messages[0].tool_calls is None


# --------------------------------------------------------------------------- #
# 审计
# --------------------------------------------------------------------------- #
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
    # 两个技能计数相同（并列），因此只校验集合不校验顺序
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


# --------------------------------------------------------------------------- #
# 工作区
# --------------------------------------------------------------------------- #
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
    # 存储名由服务端生成，绝不沿用原始文件名
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
    """带路径分隔符 / 越界构造 / 隐藏文件的输入一律拒绝。

    ⚠️ 这条闸的**重点**是"路径不能越界"。名字校验只是提前给出更清楚的报错，
    真正的边界是 `resolve()` 里的 `candidate.parent != base`。
    """
    evil_ids = [
        "../secret.txt",
        "..\\secret.txt",
        "a/b.txt",
        "sub/../x",
        ".hidden",  # 隐藏文件：扫描时会跳过，登记它只会得到一条打不开的条目
        "trailing.",  # Windows 会静默去掉结尾的点 → 库里的 id 与盘上的名字对不上
        "trailing ",
        "bad:name.txt",  # Windows 保留字符
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
    """**中文（及一般 Unicode）文件名必须放行。**

    产物是技能直接往 artifacts 目录写的，`register_artifact` 拿**文件名**当 id ——
    所以"只允许 ASCII"的白名单会让中文名产物既预览不了也另存不了
    （2026-09-28 用户报的「非法的文件标识」）。

    这条用例与上面那条是一对：**放宽的是字符集，不是越界防护**，
    后人不要把白名单改回纯 ASCII。
    """
    for name in ["业务架构图.svg", "销售 报表.xlsx", "报告（终版）.docx", "a-b_c.v2.txt"]:
        target = workspace.artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
        assert workspace.resolve(name, "artifact") == target.resolve()


@pytest.mark.asyncio
async def test_register_artifact_rejects_unusable_name(workspace):
    """名字本身不可用的产物**不许登记** —— 登记了也只是一条点开就报错的幽灵条目。"""
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
    """原始文件名里带路径时，只保留 basename 作为展示名。"""
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
    """无数据库时退化为扫描目录，功能不能丢。"""
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


# --------------------------------------------------------------------------- #
# 消息时间戳（长期记忆的时间维度）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_message_timestamps_survive_repeated_saves(repo):
    """每条消息的时间是**它自己产生的时刻**，反复落盘不会被刷成同一时刻。

    这里曾经是"一个 now 盖给整条会话的所有消息"：每轮对话都会把全部历史时间刷成
    "刚刚"，于是时间列里有值、值是错的。用户要的是"每句话都有一个准确的时间戳"，
    所以这条用例的要害是**两次保存之间旧消息的时间不变**。
    """
    record = SessionRecord(id="s1", title="时间")
    older = Message(role="user", content="昨天说的", created_at=1_700_000_000.0)
    newer = Message(role="assistant", content="刚才说的", created_at=1_700_000_600.0)

    await repo.save_session(record, [older])
    # 第二轮：会话里又追加了一条，落盘是整体重写 —— 时间必须原样保留
    await repo.save_session(record, [older, newer])

    loaded = await repo.load_messages("s1")
    assert [m.created_at for m in loaded] == [1_700_000_000.0, 1_700_000_600.0]


@pytest.mark.asyncio
async def test_legacy_rows_are_read_back_as_unknown_time(repo, db):
    """老数据的时间戳**不可信**，读回来一律当"不知道"。

    v8 之前的行是被"整表重刷"写坏的（值是最后一次保存的时刻，不是消息产生的时刻）。
    真实时刻从来没被记下来，所以这里不伪造：标成不可信、读出去就是 ``None`` ——
    宁可没有时间，也不能让模型把三个月前的旧事按"刚才"讲。
    """
    await repo.save_session(SessionRecord(id="s2", title="老会话"))
    # 手工模拟一条 v8 之前的行：不写 ts_trusted，用列默认值 0
    await db.execute(
        "INSERT INTO messages (session_id, seq, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        ("s2", 0, "user", "旧消息", 1_600_000_000.0),
    )

    loaded = await repo.load_messages("s2")

    assert loaded[0].content == "旧消息"
    assert loaded[0].created_at is None


@pytest.mark.asyncio
async def test_message_without_a_stamp_is_marked_untrusted(repo):
    """没打时间戳的消息（system / 引擎合成的提示）落盘即标不可信，读回来是 None。"""
    await repo.save_session(SessionRecord(id="s3"), [Message(role="system", content="人格")])

    loaded = await repo.load_messages("s3")

    assert loaded[0].content == "人格"
    assert loaded[0].created_at is None
