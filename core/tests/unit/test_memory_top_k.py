"""长期记忆「默认检索条数」：设置页那个值必须真的作用到检索上。

## 为什么单开一个文件

这条设置以前是个**摆设**：全仓搜下来只有三处提到它 —— schema 定义、前端类型、
设置页的输入框。**后端没有任何地方读它**，实际检索各自用硬编码
（``long_term.search`` 写死 5、``agent/history.py`` 写死 20）。

于是用户在设置里把条数从 5 改成 8，检索回来的还是 5 条 —— 看起来就是"设置不生效"，
而这类"界面上有、实际不工作"的东西恰恰是这个项目最不能忍的。

所以这里钉的不是"默认值是几"，而是**那条链路真的通了**：
设置值 → LongTermMemory.default_top_k → collection.query(n_results=...)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent.config.schemas import MemorySettings
from my_agent.memory.long_term import DEFAULT_TOP_K, LongTermMemory


class _FakeCollection:
    """假 collection：只记下 query 收到了什么参数，完全不碰 chromadb。"""

    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []

    def count(self) -> int:
        return 3

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}


def _memory(**kwargs: Any) -> tuple[LongTermMemory, _FakeCollection]:
    mem = LongTermMemory(Path("."), **kwargs)
    fake = _FakeCollection()
    # ``_ensure`` 是唯一会真去连 chromadb 的地方，换掉它就能在纯单元测试里
    # 观察"检索到底要了几条"。
    mem._ensure = lambda: fake  # type: ignore[method-assign]
    return mem, fake


def test_默认是五条():
    assert MemorySettings().vector_top_k == 5
    assert DEFAULT_TOP_K == 5


async def test_检索不传条数时用设置里的值():
    mem, fake = _memory(default_top_k=8)
    await mem.search("随便问点什么")
    assert fake.queries, "检索根本没走到 collection.query"
    assert fake.queries[0]["n_results"] == 8


async def test_调用方显式传条数时以调用方为准():
    """设置只是"默认"：技能入参（kb_search 的 top_k）优先于它。"""
    mem, fake = _memory(default_top_k=8)
    await mem.search("随便问点什么", top_k=100)
    assert fake.queries[0]["n_results"] == 100


async def test_条数被兜底成至少一条():
    """0 或负数传到 chromadb 会直接报错，而这里不该让整轮对话崩掉。"""
    mem, fake = _memory(default_top_k=0)
    assert mem.default_top_k == 1
    await mem.search("随便问点什么")
    assert fake.queries[0]["n_results"] == 1
