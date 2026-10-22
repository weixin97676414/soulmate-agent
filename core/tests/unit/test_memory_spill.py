













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








    memory.add_user("问题")
    memory.add_assistant(
        "", tool_calls=[ToolCall(id=call_id, name=name, raw_arguments="{}")]
    )
    return memory.add_tool(call_id, name, payload)





def test_full_content_is_delivered_without_any_cap(tmp_path: Path) -> None:






    memory = _memory(tmp_path, deliver_chars=200)
    payload = "A" * 30_000  

    _add_tool(memory, "call_1", payload)
    delivered = memory.get_context()[-1].content

    assert payload in delivered, "默认必须整段投递，不许有任何固定字符上限"
    assert "中间省略" not in delivered
    assert "先给出前" not in delivered
    
    assert not (tmp_path / spill_mod.SPILL_DIRNAME).exists()


def test_short_result_is_delivered_untouched(tmp_path: Path) -> None:
    memory = _memory(tmp_path)
    message = _add_tool(memory, "call_1", "短内容")

    assert memory.get_context()[-1].content == message.content


def test_without_spill_root_content_is_delivered_as_is(tmp_path: Path) -> None:

    memory = MemoryManager(max_context_tokens=200_000)
    payload = "F" * 5000

    message = _add_tool(memory, "call_1", payload)

    assert memory.get_context()[-1].content == message.content
    assert payload in message.content
    assert memory.externalize_oversized() == 0





def test_externalize_writes_full_text_and_keeps_messages_intact(tmp_path: Path) -> None:

    memory = _memory(tmp_path)
    payload = "B" * 1000

    message = _add_tool(memory, "call_1", payload)
    assert memory.externalize_oversized() == 1

    assert payload in message.content
    files = list((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert len(files) == 1
    
    assert files[0].read_text(encoding="utf-8") == message.content


def test_delivered_view_carries_a_usable_pointer(tmp_path: Path) -> None:
    memory = _memory(tmp_path, deliver_chars=200)

    _add_tool(memory, "call_1", "C" * 900)
    memory.externalize_oversized()
    delivered = memory.get_context()[-1].content

    assert "中间省略" not in delivered
    
    assert "C" * 150 in delivered
    path = next((tmp_path / spill_mod.SPILL_DIRNAME).glob("*.txt"))
    assert str(path) in delivered
    assert "offset=200" in delivered
    assert "read_tool_output" in delivered
    assert "没有丢失" in delivered


def test_delivered_boundary_is_reclosed_exactly_once(tmp_path: Path) -> None:

    memory = _memory(tmp_path, deliver_chars=200)
    _add_tool(memory, "call_1", "D" * 900)
    memory.externalize_oversized()

    delivered = memory.get_context()[-1].content

    assert delivered.count(UNTRUSTED_CLOSE) == 1
    
    assert not delivered.endswith(UNTRUSTED_CLOSE)


def test_messages_are_never_modified_by_delivery(tmp_path: Path) -> None:

    memory = _memory(tmp_path, deliver_chars=200)
    original = "E" * 900
    message = _add_tool(memory, "call_1", original)
    memory.externalize_oversized()

    memory.get_context()

    assert message.content == memory.messages[-1].content
    assert original in memory.messages[-1].content


def test_externalized_content_can_be_read_back_in_full(tmp_path: Path) -> None:

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

    
    assert "".join(collected) == memory.messages[-1].content


def test_externalize_is_idempotent(tmp_path: Path) -> None:

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

    spill_root = skill_env.paths.artifacts_dir / spill_mod.SPILL_DIRNAME
    target = spill_mod.write_spill(spill_root, "sess-1", "call_1", "J" * 500)

    result = await ReadToolOutputSkill().run(
        skill_env.ctx, **ReadToolOutputParams(path=str(target), limit=100).model_dump()
    )

    assert result["content"] == "J" * 100
    assert result["eof"] is False
    assert result["next_offset"] == 100
