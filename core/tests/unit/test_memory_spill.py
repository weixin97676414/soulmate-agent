"""无损外置（spill）的回归测试。

## 两条互相配合的规则（别搞混）

1. **默认整段给**：工具结果**不做任何预判式截断/外置**，`get_context()` 原样投递。
   用户的原话是"不要做任何截断/省略""无论多大都一次性给"。
2. **事后兜底**：只有当厂商**已经**因为超出上下文而拒绝、且压缩也救不回来时，
   才由 `externalize_oversized()` 把超长内容外置成"开头 + 续读指引"
   （全文仍在磁盘上，模型可用 `read_tool_output` 读完）。

所以下面凡是"外置"相关的断言，都要**显式调用** `externalize_oversized()`
来模拟那次兜底；不调用时内容必须是完整的。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent.llm.base import ToolCall
from my_agent.memory import spill as spill_mod
from my_agent.memory.short_term import MemoryManager
from my_agent.security.injection import UNTRUSTED_CLOSE
from my_agent.skill.builtin.output_read import ReadToolOutputParams, ReadToolOutputSkill


def _memory(tmp_path: Path, *, deliver_chars: int = 200) -> MemoryManager:
    return MemoryManager(
        max_context_tokens=200_000,
        spill_root=tmp_path / spill_mod.SPILL_DIRNAME,
        spill_session="sess-1",
        deliver_chars=deliver_chars,
    )


def _add_tool(
    memory: MemoryManager, call_id: str, payload: str, *, name: str = "t"
) -> object:
    """按**真实链路**加一条工具结果。

    ⚠️ 必须先有 ``assistant(tool_calls)`` 再 ``add_tool``：
    ``get_context`` 里有一段协议兜底，会把开头**孤立**的 tool 消息丢掉
    （``tool`` 不能出现在它对应的 ``assistant(tool_calls)`` 之前，
    否则 OpenAI/DeepSeek 一律直接 400）。直接从 ``add_tool`` 开始写测试，
    那条消息会被这道兜底丢掉，看起来就像"内容不见了"—— 其实不是。
    """
    memory.add_user("问题")
    memory.add_assistant(
        "", tool_calls=[ToolCall(id=call_id, name=name, raw_arguments="{}")]
    )
    return memory.add_tool(call_id, name, payload)


# --------------------------------------------------------------------------- #
# 规则 1：默认整段给（用户第 7 条反馈的回归）
# --------------------------------------------------------------------------- #
def test_full_content_is_delivered_without_any_cap(tmp_path: Path) -> None:
    """**核心回归**：默认投递的就是完整内容，没有 12000 这类固定上限。

    用户看到过"完整内容共 23728 字符，此处先给出前 12000 字符"—— 那个 12000
    是我们自己拍的数，属于用户明确拒绝的"人为截断"。现在只要不触发超限兜底，
    内容就一个字不少地进上下文。
    """
    memory = _memory(tmp_path, deliver_chars=200)
    payload = "A" * 30_000  # 远超旧的 12000 上限

    _add_tool(memory, "call_1", payload)
    delivered = memory.get_context()[-1].content

    assert payload in delivered, "默认必须整段投递，不许有任何固定字符上限"
    assert "中间省略" not in delivered
    assert "先给出前" not in delivered
    # 没有走到事后兜底，就不该产生任何外置文件
    assert not (tmp_path / spill_mod.SPILL_DIRNAME).exists()


def test_short_result_is_delivered_untouched(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    message = _add_tool(memory, "call_1", "短内容")

    assert memory.get_context()[-1].content == message.content


def test_without_spill_root_content_is_delivered_as_is(tmp_path: Path) -> None:
    """没配置外置位置时不做任何替换（宁可整段投递，也不给一个指向空气的路径）。"""
    memory = MemoryManager(max_context_tokens=200_000)
    payload = "F" * 5000

    message = _add_tool(memory, "call_1", payload)

    assert memory.get_context()[-1].content == message.content
    assert payload in message.content
    assert memory.externalize_oversized() == 0


# --------------------------------------------------------------------------- #
# 规则 2：事后兜底（显式调用 externalize_oversized 模拟超限重试）
# --------------------------------------------------------------------------- #
def test_externalize_writes_full_text_and_keeps_messages_intact(tmp_path: Path) -> None:
    """外置后：磁盘上有全文，`_messages` 仍然完整（界面与落库不受影响）。"""
    memory = _memory(tmp_path)
    payload = "B" * 1000

    message = _add_tool(memory, "call_1", payload)
    assert memory.externalize_oversized() == 1

    assert payload in message.content
    files = list((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert len(files) == 1
    # 外置的是**已注解**的内容（等于模型本来会看到的那份），一字不差
    assert files[0].read_text(encoding="utf-8") == message.content


def test_delivered_view_carries_a_usable_pointer(tmp_path: Path) -> None:
    memory = _memory(tmp_path, deliver_chars=200)

    _add_tool(memory, "call_1", "C" * 900)
    memory.externalize_oversized()
    delivered = memory.get_context()[-1].content

    assert "中间省略" not in delivered
    # 开头确实给到了一段（投递窗口含不可信边界的开标记，所以略少于窗口长度）
    assert "C" * 150 in delivered
    path = next((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert str(path) in delivered
    assert "offset=200" in delivered
    assert "read_tool_output" in delivered
    assert "没有丢失" in delivered


def test_delivered_boundary_is_reclosed_exactly_once(tmp_path: Path) -> None:
    """投递视图必须**重新闭合**不可信边界（闭合不上等于注入防护失效）。"""
    memory = _memory(tmp_path, deliver_chars=200)
    _add_tool(memory, "call_1", "D" * 900)
    memory.externalize_oversized()

    delivered = memory.get_context()[-1].content

    assert delivered.count(UNTRUSTED_CLOSE) == 1
    # 续读指引是**我们的指令**，必须在数据区之外（否则会被当成待处理的数据）
    assert not delivered.endswith(UNTRUSTED_CLOSE)


def test_messages_are_never_modified_by_delivery(tmp_path: Path) -> None:
    """出站视图的替换**不能**碰到 `_messages` 里那一条。"""
    memory = _memory(tmp_path, deliver_chars=200)
    original = "E" * 900
    message = _add_tool(memory, "call_1", original)
    memory.externalize_oversized()

    memory.get_context()

    assert message.content == memory.messages[-1].content
    assert original in memory.messages[-1].content


def test_externalized_content_can_be_read_back_in_full(tmp_path: Path) -> None:
    """顺着指引能把全文读回来，且**逐字符一致**（"可达"的验证点）。"""
    memory = _memory(tmp_path, deliver_chars=200)
    payload = "".join(f"第{i}段内容；" for i in range(500))

    _add_tool(memory, "call_1", payload)
    memory.externalize_oversized()
    delivered = memory.get_context()[-1].content
    path = next((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert str(path) in delivered

    collected: list[str] = []
    offset = 0
    for _ in range(500):
        piece = spill_mod.read_range(path, offset=offset, limit=997)
        collected.append(piece["content"])
        if piece["eof"]:
            break
        assert piece["next_offset"] > offset, "next_offset 必须前进"
        offset = piece["next_offset"]

    # 外置文件是"已注解"的内容，读回来应与 _messages 里的一致
    assert "".join(collected) == memory.messages[-1].content


def test_externalize_is_idempotent(tmp_path: Path) -> None:
    """重复调用不该重复写盘、也不该改变投递视图。"""
    memory = _memory(tmp_path, deliver_chars=200)
    _add_tool(memory, "call_1", "G" * 900)

    assert memory.externalize_oversized() == 1
    path = next((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    stamp = path.stat().st_mtime_ns
    first = memory.get_context()[-1].content

    assert memory.externalize_oversized() == 0
    for _ in range(3):
        assert memory.get_context()[-1].content == first
    assert path.stat().st_mtime_ns == stamp


def test_two_results_do_not_collide(tmp_path: Path) -> None:
    """两次调用的外置文件不能互相覆盖（文件名带短哈希就是为了这个）。"""
    memory = _memory(tmp_path, deliver_chars=50)
    _add_tool(memory, "call/a", "H" * 500)
    _add_tool(memory, "call?a", "I" * 500)
    assert memory.externalize_oversized() == 2

    files = list((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert len(files) == 2
    bodies = {item.read_text(encoding="utf-8") for item in files}
    assert len(bodies) == 2


@pytest.mark.asyncio
async def test_pointer_path_is_readable_through_the_skill(skill_env, tmp_path: Path) -> None:
    """指引里的路径必须是**技能真能读到**的位置（否则"落盘了"只是个承诺）。"""
    spill_root = skill_env.paths.artifacts_dir / spill_mod.SPILL_DIRNAME
    target = spill_mod.write_spill(spill_root, "sess-1", "call_1", "J" * 500)

    result = await ReadToolOutputSkill().run(
        skill_env.ctx, **ReadToolOutputParams(path=str(target), limit=100).model_dump()
    )

    assert result["content"] == "J" * 100
    assert result["eof"] is False
    assert result["next_offset"] == 100
