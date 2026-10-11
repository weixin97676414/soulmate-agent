"""群记忆库：群内共享、与搭子库互不串味、未绑搭子的会话不写记忆。

提的两件事：
1. 群聊天记录要成为「群内每个参与搭子的共同记忆」（在此之前群聊**完全不进**
   长期记忆，消息只躺在 ``group_events`` 表里）；
2. 关掉那个串台口子 —— 没绑搭子的会话以前会把内容写进**全局库**，
   而每个搭子检索时都读那个库，等于把几段无主对话塞给所有人看。
"""

from __future__ import annotations

import pytest

from my_agent.memory.long_term import chromadb_available

pytestmark = pytest.mark.skipif(
    not chromadb_available(), reason="未安装可选的 chromadb，长期记忆相关用例跳过"
)


async def test_群库与搭子库是两个库(runtime):
    """同一个字符串当群 id 和当搭子 id 用，必须落到**两个**不同的 collection。

    ⚠️ 这就是 `memory_for_group` 给 namespace 加 ``group_`` 前缀的原因：
    不然"群 g1"和"搭子 g1"会撞进同一个库，两边记忆混在一起 ——
    而那是最难查的一类问题（看起来像"记忆错乱了"）。
    """
    as_group = runtime.memory_for_group("g1")
    as_buddy = runtime.memory_for("g1")

    assert as_group is not as_buddy
    assert as_group.collection_name != as_buddy.collection_name
    assert as_group.collection_name.endswith("assistant_group_g1")
    assert as_buddy.collection_name.endswith("assistant__g1".replace("__", "_"))


async def test_同一个群两次拿到同一个实例(runtime):
    """群库也要缓存 —— 否则群里每个成员发言都新建一份，内存和句柄都会涨。"""
    assert runtime.memory_for_group("g1") is runtime.memory_for_group("g1")


async def test_群库走同一个缓存dict_换嵌入模型时一起被重建(runtime):
    """⚠️ 群库必须和搭子库共用 ``_memory_by_assistant`` 这个 dict。

    `apply_settings` 换嵌入模型时是**遍历这个 dict** 逐个 dispose + clear 的。
    群库要是自己另存一份，就永远遍历不到 —— 那个实例会一直攥着旧嵌入器，
    维度对不上，群里检索直接报错，而搭子那边却是好的（最难定位的那种故障）。
    """
    runtime.memory_for_group("g1")
    assert any(key.startswith("group_") for key in runtime._memory_by_assistant)

    settings = runtime.config.settings.model_copy(deep=True)
    settings.memory.vector_top_k = 7
    runtime.apply_settings(settings)

    assert not any(key.startswith("group_") for key in runtime._memory_by_assistant), (
        "换设置后群库实例没被丢掉，它会一直用着旧嵌入器"
    )


async def test_群发言是落进群库而不是发言人自己的库(runtime):
    """群记录是**共同**记忆：写的时候就得写进群库。"""
    seen: list[str] = []
    original = runtime.memory_for_group

    def spy(group_id):
        seen.append(group_id)
        return original(group_id)

    runtime.memory_for_group = spy  # type: ignore[method-assign]
    try:
        await runtime.archive_group_turn(group_id="g1", speaker="小王", text="定周五上线")
    finally:
        runtime.memory_for_group = original  # type: ignore[method-assign]

    assert seen == ["g1"], "群发言没有落进群库"


async def test_没绑搭子的会话不写长期记忆(runtime):
    """⚠️ 串台口子：没绑搭子的会话以前会写进全局库，而每个搭子检索时都读它。"""
    calls: list[str | None] = []
    original = runtime.memory_for

    def spy(assistant_id):
        calls.append(assistant_id)
        return original(assistant_id)

    runtime.memory_for = spy  # type: ignore[method-assign]
    try:
        await runtime.archive_turn(
            assistant_id=None,
            session_id="s1",
            user_text="我不吃香菜",
            assistant_text="记住了",
        )
    finally:
        runtime.memory_for = original  # type: ignore[method-assign]

    assert calls == [], "没绑搭子的会话仍然往记忆里写了 —— 那就是串台"


async def test_绑了搭子的会话照常写(runtime):
    """别把上面那条修过头：正常单聊必须仍然归档。"""
    calls: list[str | None] = []
    original = runtime.memory_for

    def spy(assistant_id):
        calls.append(assistant_id)
        return original(assistant_id)

    runtime.memory_for = spy  # type: ignore[method-assign]
    try:
        await runtime.archive_turn(
            assistant_id="buddy-1",
            session_id="s1",
            user_text="我不吃香菜",
            assistant_text="记住了",
        )
    finally:
        runtime.memory_for = original  # type: ignore[method-assign]

    assert calls == ["buddy-1"]


# --------------------------------------------------------------------------- #
# 单聊也能读到群记忆（产品要求）
# --------------------------------------------------------------------------- #
class _FakeMemory:
    """够 `_from_memory` 用的最小假记忆库。

    这样这一组用例不必碰 chromadb，也不必加载嵌入模型（那个 585 MB）——
    验的是"**去查了哪些库**"，与向量本身无关。
    """

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
    """群记忆也要出现在单聊里。

    ⚠️ 只查"它参与过的" —— 把没参与的群也并进来，等于让它知道别人的事。
    """
    runtime.groups.groups = [
        _group("g1", ["buddy-1", "buddy-2"]),
        _group("g2", ["buddy-2"]),
    ]

    fakes: dict[str, _FakeMemory] = {}
    original_for = runtime.memory_for
    original_group = runtime.memory_for_group
    runtime.memory_for = lambda aid: fakes.setdefault(aid or "", _FakeMemory())  # type: ignore[method-assign]
    runtime.memory_for_group = lambda gid: fakes.setdefault(f"group:{gid}", _FakeMemory())  # type: ignore[method-assign]
    try:
        # 最后一个参数是 group_id —— 传空串 = **单聊**
        await runtime.history_search._from_memory("出差", None, None, "buddy-1", "")
    finally:
        runtime.memory_for = original_for  # type: ignore[method-assign]
        runtime.memory_for_group = original_group  # type: ignore[method-assign]

    assert "group:g1" in fakes, "单聊没有去读它参与过的群记忆"
    assert "group:g2" not in fakes, "把没参与的群也读进来了"
    assert fakes["group:g1"].queries == ["出差"]


async def test_群聊时只查当前群(runtime):
    """在 g1 里发言不该看到 g2 的记忆 —— 那不叫共同记忆，叫串台。"""
    runtime.groups.groups = [
        _group("g1", ["buddy-1"]),
        _group("g2", ["buddy-1"]),
    ]

    fakes: dict[str, _FakeMemory] = {}
    original_for = runtime.memory_for
    original_group = runtime.memory_for_group
    runtime.memory_for = lambda aid: fakes.setdefault(aid or "", _FakeMemory())  # type: ignore[method-assign]
    runtime.memory_for_group = lambda gid: fakes.setdefault(f"group:{gid}", _FakeMemory())  # type: ignore[method-assign]
    try:
        await runtime.history_search._from_memory("出差", None, None, "buddy-1", "g1")
    finally:
        runtime.memory_for = original_for  # type: ignore[method-assign]
        runtime.memory_for_group = original_group  # type: ignore[method-assign]

    assert "group:g1" in fakes
    assert "group:g2" not in fakes


async def test_反查搭子参与的群(runtime):
    """`groups_for_assistant` 是上面那条链的地基。"""
    runtime.groups.groups = [
        _group("g1", ["buddy-1", "buddy-2"]),
        _group("g2", ["buddy-2"]),
        _group("g3", []),
    ]

    assert runtime.groups_for_assistant("buddy-2") == ["g1", "g2"]
    assert runtime.groups_for_assistant("buddy-1") == ["g1"]
    assert runtime.groups_for_assistant("没这个搭子") == []
    # ⚠️ 空 id 必须返回空：它会被当作"没有搭子"，而不是"所有群"
    assert runtime.groups_for_assistant(None) == []
