"""长期记忆（向量检索）与知识库技能。

**全程不联网、不下载模型**：嵌入函数是注入的假实现。

这不是偷懒——chromadb 自带的本地 ONNX 模型首次使用要下载约 80 MB，
既不能在离线环境跑，也会让测试又慢又不稳定。而「写入 → 持久化 → 检索 → 排序」
这条链路本身与嵌入函数无关，验证它不需要真模型。
"""

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
    """确定性的字符 2-gram 哈希嵌入。

    用 ``zlib.crc32`` 而不是内置 ``hash()``：后者对字符串是每进程随机加盐的，
    而 chromadb 会**把向量落盘**，换进程再读就会因为哈希不同而算出完全不同的距离。
    """
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


# --------------------------------------------------------------------------- #
# 基本读写
# --------------------------------------------------------------------------- #
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
    # 靠得最近的那条应该是工程那条
    assert "user_version" in hits[0].text
    assert hits[0].metadata.get("tags") == "工程"
    assert 0.0 < hits[0].score <= 1.0

    await memory.aclose()


@pytest.mark.asyncio
async def test_search_on_empty_returns_nothing(tmp_path):
    """空库检索要返回空列表，而不是抛异常。"""
    memory = build_memory(tmp_path)
    assert await memory.search("随便问问") == []
    await memory.aclose()


@pytest.mark.asyncio
async def test_blank_content_is_ignored(tmp_path):
    """空白内容不该写进库（会污染检索结果）。"""
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
    """换个实例重新打开，数据还在（验证真的落盘了）。"""
    first = build_memory(tmp_path)
    await first.add(["持久化的内容"])
    await first.aclose()

    second = build_memory(tmp_path)
    assert await second.count() == 1
    await second.aclose()


# --------------------------------------------------------------------------- #
# 依赖缺失时的表现
# --------------------------------------------------------------------------- #
def test_missing_service_gives_actionable_hint(tmp_path):
    """没有 memory 服务时，错误信息必须告诉用户**怎么启用**。"""
    ctx = SkillContext(paths=None, extra={})
    with pytest.raises(SkillExecutionError) as exc:
        require_memory(ctx)
    message = str(exc.value)
    # 两个可能的原因都要提到，否则用户只改一个地方、还是用不了
    assert "设置" in message
    assert "chromadb" in message


def test_disabled_service_does_not_leak_module_error():
    """服务值为 None（开关没开）时也不能冒出 'NoneType' 这种报错。"""
    ctx = SkillContext(paths=None, extra={"memory": None})
    with pytest.raises(SkillExecutionError) as exc:
        require_memory(ctx)
    assert "NoneType" not in str(exc.value)


# --------------------------------------------------------------------------- #
# 技能层
# --------------------------------------------------------------------------- #
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
    """空库时返回一句能引导用户的说明，而不是干巴巴的空数组。"""
    memory = build_memory(tmp_path)
    ctx = SkillContext(paths=None, extra={"memory": memory})

    result = await KbSearchSkill().run(ctx, query="有没有相关资料")
    assert result["results"] == []
    assert "kb_add" in result["message"]
    await memory.aclose()


# --------------------------------------------------------------------------- #
# 时间维度
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_every_memory_gets_a_timestamp(tmp_path):
    """**每条记忆都带时间**，而且调用方忘了传也会有。

    用户的要求是"记忆要有时间维度、能分清现在和以前"。兜底放在写入侧（而不是指望每个
    调用方都记得传），是因为漏传的代价要到检索时才暴露：翻出一堆"不知道什么时候的"结果。
    """
    memory = build_memory(tmp_path)
    await memory.add(["今天中午吃的拉面"], metadatas=[{"tags": "生活"}])

    hits = await memory.search("吃了什么", top_k=1)

    assert hits, "刚写进去就检索不到"
    assert hits[0].ts is not None
    assert abs(hits[0].ts - time.time()) < 60
    # 给模型的那一份要**可读**（模型算不明白 epoch 秒）
    assert re.search(r"\d{4}-\d{2}-\d{2}", hits[0].to_dict()["when"])
    await memory.aclose()


@pytest.mark.asyncio
async def test_search_respects_time_range(tmp_path):
    """按时间范围检索：只取那一段的记忆。

    这是"别把旧的当当下聊"的落点 —— 用户问"上周我们定的口径"，模型不该把三个月前的
    结论一起摆出来。
    """
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
    """技能层把 ``YYYY-MM-DD`` 翻成时间区间，且**结束日含当天**。"""
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


# --------------------------------------------------------------------------- #
# 重建（换嵌入模型后重算向量）
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rebuild_pages_through_everything_without_losing_a_single_row(tmp_path, monkeypatch):
    """重建要**分页**读，但一条都不能少、也不能重复（第 91 批，L-11）。

    为什么这条必须钉：重建是"用当前嵌入模型把所有记忆重新嵌一遍"的路径，
    它的数据安全口径是**只重算向量、原文不动**，换库靠"改名让位"（见 `_rebuild_sync`）。
    而"分页读"是这一批刚改的（原先一次 `get()` 把整库读进内存）——
    页边界一写错（偏移少加 / 多加了），表现就是**静默丢记忆或者记重复**，
    而那恰恰是这条路径最不能出的问题。

    故意把页大小压到 2 条、库里放 7 条：只要偏移算错一步，条数或内容立刻对不上。
    （`REBUILD_PAGE` 默认 1024，不压的话这条用例根本走不到第二页。）
    """
    memory = build_memory(tmp_path)
    texts = [f"第 {index} 条记忆：内容 {index}" for index in range(7)]
    await memory.add(texts, ids=[f"m{index}" for index in range(7)])

    monkeypatch.setattr(LongTermMemory, "REBUILD_PAGE", 2)
    moved = await memory.rebuild()

    assert moved == 7, "重建条数必须等于库里的条数"
    assert await memory.count() == 7, "重建后条数变了说明分页读漏了或多读了"

    hits = await memory.search("记忆", top_k=20)
    assert {hit.id for hit in hits} == {f"m{index}" for index in range(7)}
    # 原文一个字都不能变（重建只重算向量）
    assert {hit.text for hit in hits} == set(texts)
    await memory.aclose()
