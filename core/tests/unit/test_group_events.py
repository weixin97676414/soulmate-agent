















from __future__ import annotations

import pytest

from my_agent.storage.db import Database
from my_agent.storage.group_events import (
    LEGACY_THREAD_ID,
    MAX_REPLAY_EVENTS,
    GroupEventRepository,
)
from my_agent.storage.group_threads import GroupThreadRepository


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

    database = Database(tmp_path / "threads.db")
    await database.connect()
    events = GroupEventRepository(database)
    yield GroupThreadRepository(database, events), events, database
    await database.close()


@pytest.mark.asyncio
async def test_schema_creates_group_events_table(tmp_path):

    database = Database(tmp_path / "schema.db")
    await database.connect()
    tables = await database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    assert "group_events" in {row["name"] for row in tables}
    await database.close()


@pytest.mark.asyncio
async def test_schema_creates_group_threads_table(tmp_path):

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

    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "topic", {"content": "二"})
    await repo.append("g1", T1, "message", {"content": "三"})

    assert [item["seq"] for item in await repo.list_events("g1", T1)] == [1, 2]
    assert [item["seq"] for item in await repo.list_events("g1", T2)] == [1]


@pytest.mark.asyncio
async def test_两个对话的内容互不串(repo):

    await repo.append("g1", T1, "topic", {"content": "第一条对话的话题"})
    await repo.append("g1", T2, "topic", {"content": "第二条对话的话题"})

    first = await repo.list_events("g1", T1)
    second = await repo.list_events("g1", T2)

    assert [item["data"]["content"] for item in first] == ["第一条对话的话题"]
    assert [item["data"]["content"] for item in second] == ["第二条对话的话题"]


@pytest.mark.asyncio
async def test_clear_only_affects_one_thread(repo):





    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "topic", {"content": "二"})

    removed = await repo.clear("g1", T1)

    assert removed == 1
    assert await repo.list_events("g1", T1) == []
    assert len(await repo.list_events("g1", T2)) == 1


@pytest.mark.asyncio
async def test_delete_group_removes_its_events(repo):

    await repo.append("g1", T1, "topic", {"content": "一"})
    await repo.append("g1", T2, "message", {"content": "二"})

    removed = await repo.delete_group("g1")

    assert removed == 2
    assert await repo.list_events("g1", T1) == []
    assert await repo.list_events("g1", T2) == []


@pytest.mark.asyncio
async def test_replay_keeps_the_latest_when_over_limit(repo):

    total = MAX_REPLAY_EVENTS + 5
    for index in range(total):
        await repo.append("g1", T1, "message", {"content": f"第{index}条"})

    events = await repo.list_events("g1", T1)

    assert len(events) == MAX_REPLAY_EVENTS
    
    assert events[-1]["data"]["content"] == f"第{total - 1}条"
    assert [item["seq"] for item in events] == sorted(item["seq"] for item in events)


@pytest.mark.asyncio
async def test_broken_row_does_not_break_whole_history(repo, tmp_path):

    await repo.append("g1", T1, "message", {"content": "好的"})
    database = repo._db  
    await database.execute(
        "INSERT INTO group_events (group_id, thread_id, seq, event, data, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("g1", T1, 99, "message", "{坏掉的 JSON", "2026-01-01T00:00:00+00:00"),
    )

    events = await repo.list_events("g1", T1)

    assert len(events) == 1
    assert events[0]["data"]["content"] == "好的"





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

    
    assert [item["id"] for item in await repo.list_threads("g1")] == [
        second["id"],
        first["id"],
    ]

    
    await repo.touch("g1", first["id"], "2099-01-01T00:00:00+00:00")
    assert (await repo.list_threads("g1"))[0]["id"] == first["id"]


@pytest.mark.asyncio
async def test_删对话会连带删掉它的事件(threads):

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

    repo, _, _ = threads
    other = await repo.create("g2")

    assert await repo.get("g1", other["id"]) is None
    assert await repo.delete("g1", other["id"]) is False
    assert await repo.get("g2", other["id"]) is not None


@pytest.mark.asyncio
async def test_空标题会被拒绝(threads):

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





@pytest.mark.asyncio
async def test_遗留历史被认领成一条对话(threads):











    repo, events, _ = threads
    
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "升级前的记录"})
    await events.append("g1", LEGACY_THREAD_ID, "message", {"content": "也是升级前的"})

    listed = await repo.list_threads("g1")

    assert len(listed) == 1, "遗留历史应该被认领成一条对话"
    adopted = listed[0]
    assert adopted["title"] == "对话记录"
    
    replayed = await events.list_events("g1", adopted["id"])
    assert [item["data"]["content"] for item in replayed] == [
        "升级前的记录",
        "也是升级前的",
    ]


@pytest.mark.asyncio
async def test_认领只发生一次(threads):

    repo, events, _ = threads
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "老的"})

    first = await repo.list_threads("g1")
    second = await repo.list_threads("g1")

    assert len(first) == 1
    assert [item["id"] for item in second] == [item["id"] for item in first]


@pytest.mark.asyncio
async def test_已经建过对话的群里遗留历史照样被认领(threads):





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


    repo, events, _ = threads
    await events.append("g1", LEGACY_THREAD_ID, "topic", {"content": "甲群的老记录"})
    await events.append("g2", LEGACY_THREAD_ID, "topic", {"content": "乙群的老记录"})

    one = await repo.list_threads("g1")
    two = await repo.list_threads("g2")

    assert len(one) == 1 and len(two) == 1
    assert one[0]["id"] != two[0]["id"], "两条认领记录必须是不同的 id"
    assert (await events.list_events("g1", one[0]["id"]))[0]["data"]["content"] == "甲群的老记录"
    assert (await events.list_events("g2", two[0]["id"]))[0]["data"]["content"] == "乙群的老记录"
