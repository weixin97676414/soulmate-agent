








from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent.assistants.persona import (
    MEMORY_FILE,
    SOUL_FILE,
    build_persona_section,
    read_file,
    write_file,
)
from my_agent.config.schemas import AssistantProfile





UID = "u1"


@pytest.fixture
def paths():
    with tempfile.TemporaryDirectory() as tmp:
        yield SimpleNamespace(data_dir=Path(tmp))





def test_write_then_read(paths):
    write_file(paths, UID, SOUL_FILE, "# SOUL\n\n温和一点。")
    assert read_file(paths, UID, SOUL_FILE) == "# SOUL\n\n温和一点。"


def test_missing_file_reads_as_empty(paths):
    
    assert read_file(paths, "nobody", SOUL_FILE) == ""


def test_rejects_unknown_filename(paths):

    with pytest.raises(ValueError):
        write_file(paths, UID, "../../evil.md", "x")


def test_rejects_oversized_content(paths):

    with pytest.raises(ValueError):
        write_file(paths, UID, SOUL_FILE, "字" * 40_000)


def test_write_is_atomic_and_leaves_no_temp_file(paths):








    write_file(paths, UID, SOUL_FILE, "第一版。")
    write_file(paths, UID, SOUL_FILE, "第二版，长一点的内容。")

    assert read_file(paths, UID, SOUL_FILE) == "第二版，长一点的内容。"
    leftovers = [str(item) for item in Path(paths.data_dir).rglob("*.tmp")]
    assert leftovers == [], f"原子写留下了临时文件：{leftovers}"


def test_evolution_log_is_a_first_class_file(paths):






    import asyncio

    from my_agent.assistants.locked_builtins import LOCKED_PERSONA_FILES
    from my_agent.assistants.persona import ALLOWED_FILES, EVOLUTION_LOG_FILE, list_files
    from my_agent.skill.base import SkillContext
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    assert EVOLUTION_LOG_FILE in ALLOWED_FILES
    assert EVOLUTION_LOG_FILE not in LOCKED_PERSONA_FILES, "内置搭子必须能写自己的日志"
    assert read_file(paths, UID, EVOLUTION_LOG_FILE) == ""

    ctx = SkillContext(paths=paths, assistant_id=UID)
    asyncio.run(
        SelfPersonaUpdateSkill().run(
            ctx,
            file=EVOLUTION_LOG_FILE,
            old_text="",
            new_text="指标：新增 1 · 合并 0 · 冲突消解 0 · 待验证完成率 0/1",
        )
    )

    content = read_file(paths, UID, EVOLUTION_LOG_FILE)
    assert content.startswith("### "), "追加应自动带上日期标题"
    assert "指标：新增 1" in content

    entry = next(item for item in list_files(paths, UID) if item["name"] == EVOLUTION_LOG_FILE)
    assert entry["exists"] is True
    assert "指标：新增 1" in entry["content"]
    assert entry["hint"], "界面要有说明，否则用户不知道这个文件是干什么的"


def test_persona_section_empty_when_nothing_written(paths):
    
    assert build_persona_section(paths, UID) == ""
    assert build_persona_section(paths, "") == ""


def test_persona_section_includes_both(paths):
    write_file(paths, UID, SOUL_FILE, "温和。")
    write_file(paths, UID, MEMORY_FILE, "用户不喜欢客套。")

    section = build_persona_section(paths, UID)
    assert "温和。" in section
    assert "用户不喜欢客套。" in section





def test_self_update_refuses_when_old_text_is_stale():





    from my_agent.errors import SkillExecutionError
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    with tempfile.TemporaryDirectory() as tmp:
        paths = SimpleNamespace(data_dir=Path(tmp))
        write_file(paths, UID, SOUL_FILE, "用户刚手动改过的版本。")

        from my_agent.skill.base import SkillContext

        ctx = SkillContext(paths=paths, assistant_id=UID)
        with pytest.raises(SkillExecutionError):
            import asyncio

            asyncio.run(
                SelfPersonaUpdateSkill().run(
                    ctx,
                    file=SOUL_FILE,
                    old_text="模型以为的旧版本。",
                    new_text="模型想写的。",
                )
            )
        
        assert read_file(paths, UID, SOUL_FILE) == "用户刚手动改过的版本。"


def test_self_update_appends_and_replaces():
    import asyncio

    from my_agent.skill.base import SkillContext
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    with tempfile.TemporaryDirectory() as tmp:
        paths = SimpleNamespace(data_dir=Path(tmp))
        ctx = SkillContext(paths=paths, assistant_id=UID)

        
        asyncio.run(
            SelfPersonaUpdateSkill().run(ctx, file=MEMORY_FILE, old_text="", new_text="记住：别客套。")
        )
        assert "别客套。" in read_file(paths, UID, MEMORY_FILE)

        
        asyncio.run(
            SelfPersonaUpdateSkill().run(
                ctx, file=MEMORY_FILE, old_text="别客套。", new_text="别客套，直接说事。"
            )
        )
        content = read_file(paths, UID, MEMORY_FILE)
        assert "直接说事。" in content
        assert content.count("别客套") == 1


def test_self_update_requires_an_assistant():

    import asyncio

    from my_agent.errors import SkillExecutionError
    from my_agent.skill.base import SkillContext
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    with tempfile.TemporaryDirectory() as tmp:
        ctx = SkillContext(paths=SimpleNamespace(data_dir=Path(tmp)), assistant_id=None)
        with pytest.raises(SkillExecutionError):
            asyncio.run(SelfPersonaUpdateSkill().run(ctx, file=SOUL_FILE, new_text="x"))





def test_password_roundtrip_and_no_plaintext_leak():
    profile = AssistantProfile(id="LoveBuddy", name="LoveBuddy")
    assert profile.verify_persona_password("随便什么") is True  

    profile.set_persona_password("1234")
    assert profile.verify_persona_password("1234") is True
    assert profile.verify_persona_password("12345") is False

    payload = profile.to_dict()
    assert "persona_password_hash" not in payload
    assert "persona_password_salt" not in payload
    
    assert payload["persona_locked"] is True


def test_different_salts_for_same_password():

    a = AssistantProfile(id="a", name="a")
    b = AssistantProfile(id="b", name="b")
    a.set_persona_password("same")
    b.set_persona_password("same")
    assert a.persona_password_salt != b.persona_password_salt
    assert a.persona_password_hash != b.persona_password_hash
    assert a.verify_persona_password("same") and b.verify_persona_password("same")


def test_clearing_password_unlocks():
    profile = AssistantProfile(id="a", name="a")
    profile.set_persona_password("1234")
    assert profile.to_dict()["persona_locked"] is True

    profile.set_persona_password("")  
    assert profile.to_dict()["persona_locked"] is False
    assert profile.verify_persona_password("随便") is True
