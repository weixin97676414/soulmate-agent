"""群聊记录持久化的回归测试。

## 两条互不相干的约定，都在这里守着

**① 记录不能丢**（反馈 #6）：群聊记录原先只存在内存里（`runtime._group_history`），
切页面/重启即丢。做法是**把 SSE 事件流落库**（`delta` 除外），恢复时重放。

**② 一个群可以有多条对话**：事件按 `thread_id` 分成互不相干的
流，对应单聊的一个 `session`。

⚠️ 第 ② 条里最容易出事的是**升级**：v13 之前的事件没有 `thread_id`，迁移时全被
灌成空串。如果按 thread 过滤时不认领它们，用户升级后就会看到"我群里的历史全没了"。
这个文件里有专门的用例（`test_遗留历史被认领成一条对话`）守它 —— 它是这批改动里
唯一会**不可逆地弄丢用户数据**的地方。
"""

from __future__ import annotations

import pytest

from my_agent.storage.db import Database
from my_agent.storage.group_events import (
    LEGACY_THREAD_ID,
    MAX_REPLAY_EVENTS,
    GroupEventRepository,
)
from my_agent.storage.group_threads import GroupThreadRepository

#: 测试里用的两条对话，取个短名字省得每行都写一长串
T1 = "thread-1"
T2 = "thread-2"


@pytest.fixture
async def repo(tmp_path):
    database = Database(tmp_path / "groups.db")
    await database.connect()
    yield GroupEventRepository(database)
    await database.close()


@pytest.fixture
async def threads(tmp_path):
    """对话仓储（带一个连好的库）。"""
    database = Database(tmp_path / "threads.db")
    await database.connect()
    events = GroupEventRepository(database)
    yield GroupThreadRepository(database, events), events, database
    await database.close()


@pytest.mark.asyncio
async def test_schema_creates_group_events_table(tmp_path):
    """迁移到最新版本时必须建出这张表。"""
    database = Database(tmp_path / "schema.db")
    await database.connect()
    tables = await database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    assert "group_events" in {row["name"] for row in tables}
    await database.close()


@pytest.mark.asyncio
async def test_schema_creates_group_threads_table(tmp_path):
    """v13 起还要建出对话表，并且事件表上有 thread_id 列。"""
    database = Database(tmp_path / "schema13.db")
    await database.connect()
    tables = await database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    assert "group_threads" in {row["name"] for row in tables}
    columns = await database.fetch_all("PRAGMA table_info(group_events)")
    assert "thread_id" in {row["name"] for row in columns}
    await database.close()


@pytest.mark.asyncio
async def test_append_and_replay_in_order(repo):
    await repo.append("g1", T1, "topic", {"content": "帮我定个计划"})
    await repo.append("g1", T1, "speaker", {"assistant_id": "a", "name": "小A"})
    await repo.append(
        "g1", T1, "message", {"assistant_id": "a", "name": "小A", "content": "好的"}
    )

    events = await repo.list_events("g1", T1)

    assert [item["event"] for item in events] == ["topic", "speaker", "message"]
    assert [item["seq"] for item in events] == [1, 2, 3]
    assert events[0]["data"]["content"] == "帮我定个计划"
    assert events[2]["data"]["name"] == "小A"


@pytest.mark.asyncio
async def test_seq_is_per_thread(repo):
    """编号按**对话**各自从 1 开始 —— 每条对话是一条独立的流。"""
    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "topic", {"content": "二"})
    await repo.append("g1", T1, "message", {"content": "三"})

    assert [item["seq"] for item in await repo.list_events("g1", T1)] == [1, 2]
    assert [item["seq"] for item in await repo.list_events("g1", T2)] == [1]


@pytest.mark.asyncio
async def test_两个对话的内容互不串(repo):
    """这是"多条对话"的核心约定：读一条时**看不到**另一条的任何事件。"""
    await repo.append("g1", T1, "topic", {"content": "第一条对话的话题"})
    await repo.append("g1", T2, "topic", {"content": "第二条对话的话题"})

    first = await repo.list_events("g1", T1)
    second = await repo.list_events("g1", T2)

    assert [item["data"]["content"] for item in first] == ["第一条对话的话题"]
    assert [item["data"]["content"] for item in second] == ["第二条对话的话题"]


@pytest.mark.asyncio
async def test_clear_only_affects_one_thread(repo):
    """清空一条对话，另一条必须原封不动。

    以前的 `clear(group_id)` 是"清空整个群"—— 群有多条对话之后，那个语义会让
    用户"清掉一条对话，结果所有对话都没了"。
    """
    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "topic", {"content": "二"})

    removed = await repo.clear("g1", T1)

    assert removed == 1
    assert await repo.list_events("g1", T1) == []
    assert len(await repo.list_events("g1", T2)) == 1


@pytest.mark.asyncio
async def test_delete_group_removes_its_events(repo):
    """删群清**全部**对话的事件：`thread_id=None` 才是"整个群"。"""
    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "message", {"content": "二"})

    removed = await repo.delete_group("g1")

    assert removed == 2
    assert await repo.list_events("g1", T1) == []
    assert await repo.list_events("g1", T2) == []


@pytest.mark.asyncio
async def test_replay_keeps_the_latest_when_over_limit(repo):
    """超过上限时保留**最近**的，而不是最早的 —— 否则用户永远看不到最新一轮。"""
    total = MAX_REPLAY_EVENTS + 5
    for index in range(total):
        await repo.append("g1", T1, "message", {"content": f"第{index}条"})

    events = await repo.list_events("g1", T1)

    assert len(events) == MAX_REPLAY_EVENTS
    # 升序返回，且末尾是最后写入的那条
    assert events[-1]["data"]["content"] == f"第{total - 1}条"
    assert [item["seq"] for item in events] == sorted(item["seq"] for item in events)


@pytest.mark.asyncio
async def test_broken_row_does_not_break_whole_history(repo, tmp_path):
    """单条 JSON 坏掉时跳过它，而不是让整个历史打不开。"""
    await repo.append("g1", T1, "message", {"content": "好的"})
    database = repo._db  # noqa: SLF001 - 测试里故意塞一条坏数据
    await database.execute(
        "INSERT INTO group_events (group_id, thread_id, seq, event, data, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("g1", T1, 99, "message", "{坏掉的 JSON", "2026-01-01T00:00:00+00:00"),
    )

    events = await repo.list_events("g1", T1)

    assert len(events) == 1
    assert events[0]["data"]["content"] == "好的"


# --------------------------------------------------------------------------- #
# 对话表本身
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_新建对话能查到且标题可用(threads):
    repo, _, _ = threads

    created = await repo.create("g1", "聊聊计划")
    listed = await repo.list_threads("g1")

    assert [item["id"] for item in listed] == [created["id"]]
    assert listed[0]["title"] == "聊聊计划"


@pytest.mark.asyncio
async def test_列表里最近有动静的排前面(threads):
    repo, _, _ = threads
    first = await repo.create("g1", "先建的")
    second = await repo.create("g1", "后建的")

    # 默认按 updated_at 降序：后建的在前
    assert [item["id"] for item in await repo.list_threads("g1")] == [
        second["id"],
        first["id"],
    ]

    # 推一下第一条的时间，它应该排到最前
    await repo.touch("g1", first["id"], "2099-01-01T00:00:00+00:00")
    assert (await repo.list_threads("g1"))[0]["id"] == first["id"]


@pytest.mark.asyncio
async def test_删对话会连带删掉它的事件(threads):
    """不连带删的话那些事件永远读不到、还占着库 —— 属于纯泄漏。"""
    repo, events, _ = threads
    keep = await repo.create("g1")
    drop = await repo.create("g1")
    await events.append("g1", keep["id"], "topic", {"content": "留着"})
    await events.append("g1", drop["id"], "topic", {"content": "要删"})

    assert await repo.delete("g1", drop["id"]) is True

    assert [item["id"] for item in await repo.list_threads("g1")] == [keep["id"]]
    assert await events.list_events("g1", drop["id"]) == []
    assert len(await events.list_events("g1", keep["id"])) == 1


@pytest.mark.asyncio
async def test_别的群的对话拿不到也删不掉(threads):
    """`get` / `delete` 都要同时匹配 group_id：只按 id 的话，A 群能碰 B 群的对话。"""
    repo, _, _ = threads
    other = await repo.create("g2")

    assert await repo.get("g1", other["id"]) is None
    assert await repo.delete("g1", other["id"]) is False
    assert await repo.get("g2", other["id"]) is not None


@pytest.mark.asyncio
async def test_空标题会被拒绝(threads):
    """列表里出现一条没名字的对话是无法向用户解释的。"""
    repo, _, _ = threads
    created = await repo.create("g1", "有名字")

    assert await repo.rename("g1", created["id"], "   ") is False
    assert (await repo.get("g1", created["id"]))["title"] == "有名字"


@pytest.mark.asyncio
async def test_删群时对话也一起清(threads):
    repo, _, _ = threads
    await repo.create("g1")
    await repo.create("g1")
    await repo.create("g2")

    await repo.delete_group("g1")

    assert await repo.list_threads("g1") == []
    assert len(await repo.list_threads("g2")) == 1


# --------------------------------------------------------------------------- #
# 升级路径：**这是本次唯一会不可逆丢数据的地方**
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_遗留历史被认领成一条对话(threads):
    """v13 之前的事件（thread_id = 空串）必须被收进一条真实对话里。

    ## ⚠️ 这条用例存在的唯一理由

    迁移给 `group_events` 加 `thread_id` 时用的是 `DEFAULT ''`，所以升级后**既有
    的全部历史**都挂在空串上。此后所有读路径都按 `thread_id` 过滤 —— 如果没人
    把它们改挂到一个真实 id 上，那些事件就再也匹配不到任何对话。

    用户看到的现象是：**"我升级之后，群里的历史记录全没了。"**
    它不会报错、不会丢文件，只是安静地查不出来 —— 所以必须有测试钉住。
    """
    repo, events, _ = threads
    # 模拟升级前的库：事件直接写空串（新代码不会这么做，这里是造数据）
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "升级前的记录"})
    await events.append("g1", LEGACY_THREAD_ID, "message", {"content": "也是升级前的"})

    listed = await repo.list_threads("g1")

    assert len(listed) == 1, "遗留历史应该被认领成一条对话"
    adopted = listed[0]
    assert adopted["title"] == "对话记录"
    # 事件改挂到了新 id 上，内容一条都没少
    replayed = await events.list_events("g1", adopted["id"])
    assert [item["data"]["content"] for item in replayed] == [
        "升级前的记录",
        "也是升级前的",
    ]


@pytest.mark.asyncio
async def test_认领只发生一次(threads):
    """第二次列列表时不该再多出一条"对话记录"。"""
    repo, events, _ = threads
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "老的"})

    first = await repo.list_threads("g1")
    second = await repo.list_threads("g1")

    assert len(first) == 1
    assert [item["id"] for item in second] == [item["id"] for item in first]


@pytest.mark.asyncio
async def test_已经建过对话的群里遗留历史照样被认领(threads):
    """判据是"事件表里还有空串的行"，不是"对话表里有没有行"。

    用户可能先建了新对话才翻到历史；若只看"有没有对话"，那批老事件就永远
    认领不掉 —— 表现为"历史记录不见了"，而且越用越找不回来。
    """
    repo, events, _ = threads
    fresh = await repo.create("g1", "新建的对话")
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "老的"})

    listed = await repo.list_threads("g1")

    assert len(listed) == 2, "新对话 + 认领出来的历史，各一条"
    ids = {item["id"] for item in listed}
    assert fresh["id"] in ids
    legacy = next(item for item in listed if item["title"] == "对话记录")
    assert len(await events.list_events("g1", legacy["id"])) == 1


@pytest.mark.asyncio
async def test_不同群各自认领自己的遗留历史(threads):
    """两个群的老事件都挂在空串上，但对话 id 是**全局唯一**的主键 ——
    两个群不能共用同一条"对话记录"，否则第二个群的历史会读到第一个群的。"""
    repo, events, _ = threads
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "甲群的老记录"})
    await events.append("g2", LEGACY_THREAD_ID, "topic", {"content": "乙群的老记录"})

    one = await repo.list_threads("g1")
    two = await repo.list_threads("g2")

    assert len(one) == 1 and len(two) == 1
    assert one[0]["id"] != two[0]["id"], "两条认领记录必须是不同的 id"
    assert (await events.list_events("g1", one[0]["id"]))[0]["data"]["content"] == "甲群的老记录"
    assert (await events.list_events("g2", two[0]["id"]))[0]["data"]["content"] == "乙群的老记录"
