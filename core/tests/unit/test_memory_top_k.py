














from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent.config.schemas import MemorySettings
from my_agent.memory.long_term import DEFAULT_TOP_K, LongTermMemory


class _FakeCollection:


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
    
    
    mem._ensure = lambda: fake  
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

    mem, fake = _memory(default_top_k=8)
    await mem.search("随便问点什么", top_k=100)
    assert fake.queries[0]["n_results"] == 100


async def test_条数被兜底成至少一条():

    mem, fake = _memory(default_top_k=0)
    assert mem.default_top_k == 1
    await mem.search("随便问点什么")
    assert fake.queries[0]["n_results"] == 1
