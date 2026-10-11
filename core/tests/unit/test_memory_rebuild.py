"""换嵌入模型之后，旧记忆会不会丢。

这是用户最担心的那类失败 ——「我换了个模型，之前存的东西是不是没了？」
答案是不会：库里除了向量还存着**原文**，向量只是原文的一份索引，索引可以重算。
这批用例就是把那条重建链路钉住。

⚠️ 全程用假嵌入器、不联网、不下载模型：这里验的是**重建逻辑**，与用哪个模型无关。
唯一需要能控制的是**维度**——所以假嵌入器的维度是参数。
"""

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
    """造一个指定维度的确定性嵌入器（字符 2-gram 哈希）。

    用 ``zlib.crc32`` 而不是内置 ``hash()``：后者对字符串是每进程随机加盐的，
    而 chromadb 会把向量落盘，换进程再读就会算出完全不同的距离。
    """

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
    """同一个目录、同一个库名 —— 模拟"用户换了模型，别的什么都没动"。"""
    return LongTermMemory(
        tmp_path / "vectors",
        collection="test-kb",
        embedder=embedder_of(dim),
        embedding_signature=sig,
    )


async def test_新库直接认领签名(tmp_path):
    """刚建的库没什么可重建的，认领一下就行。"""
    fresh = build(tmp_path, dim=128, sig="builtin")
    assert await fresh.sync_signature() == "empty"
    assert not fresh.rebuilding


async def test_换模型后签名不一致会被发现并触发重建(tmp_path):
    # ⚠️ 这里不用再显式调一次 ``sync_signature``：``add`` 内部已经做过第一次检查
    # （新库在那时就认领了签名），而这项检查每个实例**只做一次** ——
    # 再调一次会（正确地）返回 "skipped"。
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    assert await before.count() == 3

    # 用户换成另一个模型（维度不同）
    after = build(tmp_path, dim=64, sig="ollama|http://127.0.0.1:11434|nomic-embed-text")
    assert await after.sync_signature() == "stale"
    assert after.rebuilding, "发现嵌入方式变了，却没开始重建"

    # 等后台那个任务跑完 —— 直接 await 它是为了让测试能观察到结果
    # （否则测试结束时任务可能被 GC 掉，重建结果就断不到了）
    moved = await after._rebuild_task  # noqa: SLF001 - 就是来验它搬了多少条的
    assert moved == 3


async def test_重建只换向量_原文一条不少(tmp_path):
    """这是这批改动的**核心承诺**：换模型不会让记忆消失。"""
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    after = build(tmp_path, dim=64, sig="其他模型")
    assert await after.rebuild() == 3

    # 用**新模型**能检索到旧记忆 —— 说明向量确实是重算过的（原向量维度对不上）
    hits = await after.search("出差", top_k=5)
    assert {hit.text for hit in hits} & set(MEMORIES), "换模型后检索不到旧记忆了"
    assert await after.count() == 3


async def test_签名一致时什么都不做(tmp_path):
    """模型没换就不该重建 —— 重建要重跑全部嵌入，白跑一次代价很大。"""
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    same = build(tmp_path, dim=128, sig="builtin")
    assert await same.sync_signature() == "ok"
    assert not same.rebuilding
    assert await same.count() == 3


async def test_老库没有签名时先认领_不盲目重建(tmp_path):
    """这项功能之前建的库没有签名 —— 无从判断旧维度，先认领，别乱重建。"""
    legacy = build(tmp_path, dim=128, sig="")
    await legacy.add(MEMORIES)
    assert await legacy.sync_signature() == "skipped"  # 没签名 = 不启用检查

    claimed = build(tmp_path, dim=128, sig="builtin")
    assert await claimed.sync_signature() == "adopted"
    assert not claimed.rebuilding
    assert await claimed.count() == 3


async def test_重建失败时旧数据必须原样还在(tmp_path):
    """重建半路炸掉（嵌入服务连不上）—— 旧库一条都不能少。

    这是整个设计里最要紧的一条：宁可这次没重建成功，也不能把用户攒下来的记忆弄丢。
    """
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    broken = build(tmp_path, dim=64, sig="其他模型")

    def boom(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("嵌入服务连不上")

    broken._embedder = boom  # type: ignore[assignment]  # noqa: SLF001 - 就是为了制造失败

    assert await broken.rebuild() == 0

    # 旧库原封不动：条数没变，而且**用原来的模型**照样查得到
    assert await before.count() == 3
    assert await before.search("出差", top_k=5)


async def test_重建期间检索直接跳过_而不是假装没有记忆(tmp_path):
    """重建中不能返回"没查到" —— 那会让用户以为记忆丢了。

    上层（``agent/history.py``）靠 ``rebuilding`` 区分"正在重建"与"真的没有"。
    """
    before = build(tmp_path, dim=128, sig="builtin")
    await before.add(MEMORIES)
    await before.sync_signature()

    after = build(tmp_path, dim=64, sig="其他模型")
    assert await after.sync_signature() == "stale"
    # 紧接着检索：这时后台重建还没跑完
    assert await after.search("出差", top_k=5) == []

    await after._rebuild_task  # noqa: SLF001 - 等它建完
    assert not after.rebuilding
    assert await after.search("出差", top_k=5), "重建完成后仍然查不到"


async def test_重建完成会回调一次(tmp_path):
    """界面那句"长期记忆已整理好"就挂在这个回调上 —— 不回调就永远不弹。

    ⚠️ 别把它当成可有可无的装饰：重建期间检索是跳过的，用户这时候问旧事会得到
    "没有相关记忆"；不主动说一声，他会以为换模型把记忆弄丢了。
    """
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
    """空库（或重建失败）不该弹"已整理好 N 条" —— 那是在说一件没发生的事。"""
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
