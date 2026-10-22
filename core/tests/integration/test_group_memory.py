








from __future__ import annotations

import pytest

from my_agent.memory.long_term import chromadb_available

pytestmark = pytest.mark.skipif(
    not chromadb_available(), reason="未安装可选的 chromadb，长期记忆相关用例跳过"
)


async def test_群库与搭子库是两个库(runtime):






    as_group = runtime.memory_for_group("g1")
    as_buddy = runtime.memory_for("g1")

    assert as_group is not as_buddy
    assert as_group.collection_name != as_buddy.collection_name
    assert as_group.collection_name.endswith("assistant_group_g1")
    assert as_buddy.collection_name.endswith("assistant__g1".replace("__", "_"))


async def test_同一个群两次拿到同一个实例(runtime):

    assert runtime.memory_for_group("g1") is runtime.memory_for_group("g1")


async def test_群库走同一个缓存dict_换嵌入模型时一起被重建(runtime):






    runtime.memory_for_group("g1")
    assert any(key.startswith("group_") for key in runtime._memory_by_assistant)

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.vector_top_k = 7
    runtime.apply_settings(settings)

    assert not any(key.startswith("group_") for key in runtime._memory_by_assistant), (
        "换设置后群库实例没被丢掉，它会一直用着旧嵌入器"
    )


async def test_群发言是落进群库而不是发言人自己的库(runtime):

    seen: list[str] = []
    original = runtime.memory_for_group

    def spy(group_id):
        seen.append(group_id)
        return original(group_id)

    runtime.memory_for_group = spy  
    try:
        await runtime.archive_group_turn(group_id="g1", speaker="小王", text="定周五上线")
    finally:
        runtime.memory_for_group = original  

    assert seen == ["g1"], "群发言没有落进群库"


async def test_没绑搭子的会话不写长期记忆(runtime):

    calls: list[str | None] = []
    original = runtime.memory_for

    def spy(assistant_id):
        calls.append(assistant_id)
        return original(assistant_id)

    runtime.memory_for = spy  
    try:
        await runtime.archive_turn(
            assistant_id=None,
            session_id="s1",
            user_text="我不吃香菜",
            assistant_text="记住了",
        )
    finally:
        runtime.memory_for = original  

    assert calls == [], "没绑搭子的会话仍然往记忆里写了 —— 那就是串台"


async def test_绑了搭子的会话照常写(runtime):

    calls: list[str | None] = []
    original = runtime.memory_for

    def spy(assistant_id):
        calls.append(assistant_id)
        return original(assistant_id)

    runtime.memory_for = spy  
    try:
        await runtime.archive_turn(
            assistant_id="buddy-1",
            session_id="s1",
            user_text="我不吃香菜",
            assistant_text="记住了",
        )
    finally:
        runtime.memory_for = original  

    assert calls == ["buddy-1"]





class _FakeMemory:






    available = True
    rebuilding = False

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query, **_kwargs):
        self.queries.append(query)
        return []


def _group(group_id: str, members: list[str]):
    from my_agent.config.schemas import GroupProfile

    return GroupProfile(id=group_id, name=f"群{group_id}", member_assistant_ids=members)


async def test_单聊时只并入它参与过的那些群(runtime):




    runtime.groups.groups = [
        _group("g1", ["buddy-1", "buddy-2"]),
        _group("g2", ["buddy-2"]),
    ]

    fakes: dict[str, _FakeMemory] = {}
    original_for = runtime.memory_for
    original_group = runtime.memory_for_group
    runtime.memory_for = lambda aid: fakes.setdefault(aid or "", _FakeMemory())  
    runtime.memory_for_group = lambda gid: fakes.setdefault(f"group:{gid}", _FakeMemory())  
    try:
        
        await runtime.history_search._from_memory("出差", None, None, "buddy-1", "")
    finally:
        runtime.memory_for = original_for  
        runtime.memory_for_group = original_group  

    assert "group:g1" in fakes, "单聊没有去读它参与过的群记忆"
    assert "group:g2" not in fakes, "把没参与的群也读进来了"
    assert fakes["group:g1"].queries == ["出差"]


async def test_群聊时只查当前群(runtime):

    runtime.groups.groups = [
        _group("g1", ["buddy-1"]),
        _group("g2", ["buddy-1"]),
    ]

    fakes: dict[str, _FakeMemory] = {}
    original_for = runtime.memory_for
    original_group = runtime.memory_for_group
    runtime.memory_for = lambda aid: fakes.setdefault(aid or "", _FakeMemory())  
    runtime.memory_for_group = lambda gid: fakes.setdefault(f"group:{gid}", _FakeMemory())  
    try:
        await runtime.history_search._from_memory("出差", None, None, "buddy-1", "g1")
    finally:
        runtime.memory_for = original_for  
        runtime.memory_for_group = original_group  

    assert "group:g1" in fakes
    assert "group:g2" not in fakes


async def test_反查搭子参与的群(runtime):

    runtime.groups.groups = [
        _group("g1", ["buddy-1", "buddy-2"]),
        _group("g2", ["buddy-2"]),
        _group("g3", []),
    ]

    assert runtime.groups_for_assistant("buddy-2") == ["g1", "g2"]
    assert runtime.groups_for_assistant("buddy-1") == ["g1"]
    assert runtime.groups_for_assistant("没这个搭子") == []
    
    assert runtime.groups_for_assistant(None) == []
