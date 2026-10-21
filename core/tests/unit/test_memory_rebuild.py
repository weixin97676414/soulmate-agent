









from __future__ import annotations

import math
import zlib

import pytest

from my_agent.memory.long_term import LongTermMemory, chromadb_available

pytestmark = pytest.mark.skipif(
    not chromadb_available(), reason="未安装可选的 chromadb，长期记忆相关用例跳过"
)

MEMORIES = [
    "我住在杭州，平时写 Python",
    "下周三要去上海出差",
    "我不吃香菜",
]


def embedder_of(dim: int):






    def embed(texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dim
            normalized = "".join(text.split()).lower()
            for index in range(max(len(normalized) - 1, 1)):
                gram = normalized[index : index + 2] or normalized
                vec[zlib.crc32(gram.encode("utf-8")) % dim] += 1.0
            norm = math.sqrt(sum(value * value for value in vec)) or 1.0
            vectors.append([value / norm for value in vec])
        return vectors

    return embed


def build(tmp_path, *, dim: int, sig: str) -> LongTermMemory:

    return LongTermMemory(
        tmp_path / "vectors",
        collection="test-kb",
        embedder=embedder_of(dim),
        embedding_signature=sig,
    )


async def test_新库直接认领签名(tmp_path):

    fresh = build(tmp_path, dim=128, sig="builtin")
    assert await fresh.sync_signature() == "empty"
    assert not fresh.rebuilding


async def test_换模型后签名不一致会被发现并触发重建(tmp_path):
    
    
    
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    assert await before.count() == 3

    
    after = build(tmp_path, dim=64, sig="ollama|http://127.0.0.1:11434|nomic-embed-text")
    assert await after.sync_signature() == "stale"
    assert after.rebuilding, "发现嵌入方式变了，却没开始重建"

    
    
    moved = await after._rebuild_task  
    assert moved == 3


async def test_重建只换向量_原文一条不少(tmp_path):

    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    after = build(tmp_path, dim=64, sig="其他模型")
    assert await after.rebuild() == 3

    
    hits = await after.search("出差", top_k=5)
    assert {hit.text for hit in hits} & set(MEMORIES), "换模型后检索不到旧记忆了"
    assert await after.count() == 3


async def test_签名一致时什么都不做(tmp_path):

    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    same = build(tmp_path, dim=128, sig="builtin")
    assert await same.sync_signature() == "ok"
    assert not same.rebuilding
    assert await same.count() == 3


async def test_老库没有签名时先认领_不盲目重建(tmp_path):

    legacy = build(tmp_path, dim=128, sig="")
    await legacy.add(MEMORIES)
    assert await legacy.sync_signature() == "skipped"  

    claimed = build(tmp_path, dim=128, sig="builtin")
    assert await claimed.sync_signature() == "adopted"
    assert not claimed.rebuilding
    assert await claimed.count() == 3


async def test_重建失败时旧数据必须原样还在(tmp_path):




    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    broken = build(tmp_path, dim=64, sig="其他模型")

    def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("嵌入服务连不上")

    broken._embedder = boom  

    assert await broken.rebuild() == 0

    
    assert await before.count() == 3
    assert await before.search("出差", top_k=5)


async def test_重建期间检索直接跳过_而不是假装没有记忆(tmp_path):




    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    after = build(tmp_path, dim=64, sig="其他模型")
    assert await after.sync_signature() == "stale"
    
    assert await after.search("出差", top_k=5) == []

    await after._rebuild_task  
    assert not after.rebuilding
    assert await after.search("出差", top_k=5), "重建完成后仍然查不到"


async def test_重建完成会回调一次(tmp_path):





    seen: list[int] = []
    before = LongTermMemory(
        tmp_path / "vectors",
        collection="test-kb",
        embedder=embedder_of(128),
        embedding_signature="builtin",
    )
    await before.add(MEMORIES)

    after = LongTermMemory(
        tmp_path / "vectors",
        collection="test-kb",
        embedder=embedder_of(64),
        embedding_signature="其他模型",
        on_rebuilt=seen.append,
    )
    assert await after.rebuild() == 3
    assert seen == [3], "重建完成没有回调，界面上就不会有任何提示"


async def test_没有东西可重建时不回调(tmp_path):

    seen: list[int] = []
    empty = LongTermMemory(
        tmp_path / "vectors",
        collection="test-kb",
        embedder=embedder_of(128),
        embedding_signature="builtin",
        on_rebuilt=seen.append,
    )
    assert await empty.rebuild() == 0
    assert seen == []
