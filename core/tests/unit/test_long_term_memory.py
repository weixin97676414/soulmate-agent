








from __future__ import annotations

import math
import re
import time
import zlib

import pytest

from my_agent.errors import SkillExecutionError
from my_agent.memory.long_term import LongTermMemory, chromadb_available
from my_agent.skill.base import SkillContext
from my_agent.skill.builtin.knowledge import (
    KbAddSkill,
    KbSearchSkill,
    KbStatsSkill,
    require_memory,
)
from my_agent.utils.timefmt import format_day

pytestmark = pytest.mark.skipif(
    not chromadb_available(), reason="未安装可选的 chromadb，长期记忆相关用例跳过"
)

DIM = 128


def fake_embedder(texts: list[str]) -> list[list[float]]:





    vectors: list[list[float]] = []
    for text in texts:
        vec = [0.0] * DIM
        normalized = "".join(text.split()).lower()
        for index in range(max(len(normalized) - 1, 1)):
            gram = normalized[index : index + 2] or normalized
            vec[zlib.crc32(gram.encode("utf-8")) % DIM] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        vectors.append([value / norm for value in vec])
    return vectors


def build_memory(tmp_path, **kwargs) -> LongTermMemory:
    return LongTermMemory(
        tmp_path / "vectors", collection="test-kb", embedder=fake_embedder, **kwargs
    )





@pytest.mark.asyncio
async def test_add_and_search_round_trip(tmp_path):
    memory = build_memory(tmp_path)
    await memory.add(
        [
            "SQLite 的 user_version 用来记录数据库迁移版本",
            "今天中午吃了拉面，花了 35 元",
        ],
        metadatas=[{"tags": "工程"}, {"tags": "生活"}],
    )
    assert await memory.count() == 2

    hits = await memory.search("数据库迁移版本怎么记录", top_k=2)
    assert hits, "明明存过相关内容却检索不到"
    
    assert "user_version" in hits[0].text
    assert hits[0].metadata.get("tags") == "工程"
    assert 0.0 < hits[0].score <= 1.0

    await memory.aclose()


@pytest.mark.asyncio
async def test_search_on_empty_returns_nothing(tmp_path):

    memory = build_memory(tmp_path)
    assert await memory.search("随便问问") == []
    await memory.aclose()


@pytest.mark.asyncio
async def test_blank_content_is_ignored(tmp_path):

    memory = build_memory(tmp_path)
    ids = await memory.add(["   ", "", "\n"])
    assert ids == []
    assert await memory.count() == 0
    await memory.aclose()


@pytest.mark.asyncio
async def test_forget_and_clear(tmp_path):
    memory = build_memory(tmp_path)
    ids = await memory.add(["第一条", "第二条"])
    assert len(ids) == 2

    assert await memory.forget([ids[0]]) == 1
    assert await memory.count() == 1

    assert await memory.clear() == 1
    assert await memory.count() == 0
    await memory.aclose()


@pytest.mark.asyncio
async def test_data_survives_reopen(tmp_path):

    first = build_memory(tmp_path)
    await first.add(["持久化的内容"])
    await first.aclose()

    second = build_memory(tmp_path)
    assert await second.count() == 1
    await second.aclose()





def test_missing_service_gives_actionable_hint(tmp_path):

    ctx = SkillContext(paths=None, extra={})
    with pytest.raises(SkillExecutionError) as exc:
        require_memory(ctx)
    message = str(exc.value)
    
    assert "设置" in message
    assert "chromadb" in message


def test_disabled_service_does_not_leak_module_error():

    ctx = SkillContext(paths=None, extra={"memory": None})
    with pytest.raises(SkillExecutionError) as exc:
        require_memory(ctx)
    assert "NoneType" not in str(exc.value)





@pytest.mark.asyncio
async def test_kb_skills_end_to_end(tmp_path):
    memory = build_memory(tmp_path)
    ctx = SkillContext(paths=None, extra={"memory": memory})

    written = await KbAddSkill().run(ctx, content="项目用 Electron 打包成 MSI", tags=["工程"])
    assert written["ok"] is True

    found = await KbSearchSkill().run(ctx, query="客户端怎么打包", top_k=3)
    assert found["results"]
    assert "Electron" in found["results"][0]["text"]

    stats = await KbStatsSkill().run(ctx)
    assert stats["count"] == 1
    await memory.aclose()


@pytest.mark.asyncio
async def test_kb_search_on_empty_kb_says_so(tmp_path):

    memory = build_memory(tmp_path)
    ctx = SkillContext(paths=None, extra={"memory": memory})

    result = await KbSearchSkill().run(ctx, query="有没有相关资料")
    assert result["results"] == []
    assert "kb_add" in result["message"]
    await memory.aclose()





@pytest.mark.asyncio
async def test_every_memory_gets_a_timestamp(tmp_path):





    memory = build_memory(tmp_path)
    await memory.add(["今天中午吃的拉面"], metadatas=[{"tags": "生活"}])

    hits = await memory.search("吃了什么", top_k=1)

    assert hits, "刚写进去就检索不到"
    assert hits[0].ts is not None
    assert abs(hits[0].ts - time.time()) < 60
    
    assert re.search(r"\d{4}-\d{2}-\d{2}", hits[0].to_dict()["when"])
    await memory.aclose()


@pytest.mark.asyncio
async def test_search_respects_time_range(tmp_path):





    memory = build_memory(tmp_path)
    now = time.time()
    await memory.add(["三个月前定的是每周五交周报"], metadatas=[{"ts": now - 90 * 86400}])
    await memory.add(["上周改成了每周一交周报"], metadatas=[{"ts": now - 5 * 86400}])

    recent = await memory.search("周报什么时候交", top_k=5, since=now - 14 * 86400)

    assert recent, "最近两周内明明有一条"
    assert all(hit.ts is not None and hit.ts >= now - 14 * 86400 for hit in recent)
    assert all("三个月前" not in hit.text for hit in recent)
    await memory.aclose()


@pytest.mark.asyncio
async def test_kb_search_accepts_date_range(tmp_path):

    memory = build_memory(tmp_path)
    ctx = SkillContext(paths=None, extra={"memory": memory})

    today = format_day(time.time())
    await KbAddSkill().run(ctx, content="今天定的排期是周三上线")

    found = await KbSearchSkill().run(ctx, query="排期", since=today, until=today)
    assert found["results"], "今天的区间应该能查到刚存的那条"

    long_ago = format_day(time.time() - 30 * 86400)
    empty = await KbSearchSkill().run(ctx, query="排期", since=long_ago, until=long_ago)
    assert empty["results"] == [], "30 天前那天不该查出今天写的东西"
    await memory.aclose()





@pytest.mark.asyncio
async def test_rebuild_pages_through_everything_without_losing_a_single_row(tmp_path, monkeypatch):











    memory = build_memory(tmp_path)
    texts = [f"第 {index} 条记忆：内容 {index}" for index in range(7)]
    await memory.add(texts, ids=[f"m{index}" for index in range(7)])

    monkeypatch.setattr(LongTermMemory, "REBUILD_PAGE", 2)
    moved = await memory.rebuild()

    assert moved == 7, "重建条数必须等于库里的条数"
    assert await memory.count() == 7, "重建后条数变了说明分页读漏了或多读了"

    hits = await memory.search("记忆", top_k=20)
    assert {hit.id for hit in hits} == {f"m{index}" for index in range(7)}
    
    assert {hit.text for hit in hits} == set(texts)
    await memory.aclose()
