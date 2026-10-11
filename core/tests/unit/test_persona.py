"""助手的人格 / 记忆文件，以及人格锁。

重点测的是两类**错了不会报错**的事：

1. **覆盖风险**：模型手里的原文过期时，直接整份覆盖会吃掉用户刚做的修改，
   而且**没有任何提示**。所以"原文对不上就必须失败"。
2. **口令材料**：哈希与盐不能出现在下发给界面的数据里。
"""

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

# ⚠️ 测试对象**不要**用四位内置搭子的 id（``soulmate`` / ``LoveBuddy`` /
# ``RelationBuddy`` / ``BuddyManager``）：它们的人设文件是**写死**的
# ，``write_file`` 会直接拒绝 —— 那样测的就不是"文件读写"
# 这条链路了。用用户自建搭子那种 id。
UID = "u1"


@pytest.fixture
def paths():
    with tempfile.TemporaryDirectory() as tmp:
        yield SimpleNamespace(data_dir=Path(tmp))


# --------------------------------------------------------------------------- #
# 文件读写
# --------------------------------------------------------------------------- #
def test_write_then_read(paths):
    write_file(paths, UID, SOUL_FILE, "# SOUL\n\n温和一点。")
    assert read_file(paths, UID, SOUL_FILE) == "# SOUL\n\n温和一点。"


def test_missing_file_reads_as_empty(paths):
    # 首次使用文件不存在是常态，不该抛异常
    assert read_file(paths, "nobody", SOUL_FILE) == ""


def test_rejects_unknown_filename(paths):
    """文件名必须走白名单 —— 否则等于"往数据目录写任意文件"。"""
    with pytest.raises(ValueError):
        write_file(paths, UID, "../../evil.md", "x")


def test_rejects_oversized_content(paths):
    """它会被塞进每次对话的提示词，不设上限等于让人撑爆上下文。"""
    with pytest.raises(ValueError):
        write_file(paths, UID, SOUL_FILE, "字" * 40_000)


def test_write_is_atomic_and_leaves_no_temp_file(paths):
    """写盘必须**原子**（第 87 批，M-15）。

    这些文件会被拼进**每一轮**的 system 提示词（尤其 SOUL / IDENTITY），
    写一半崩溃会留下**截断的人格** —— 而下次启动会照常读它，
    用户只会觉得"搭子突然变了个样"，且没有任何报错。
    所以实现走的是"同目录临时文件 + `os.replace`"，这里钉住两件事：
    ① 覆盖之后内容完整；② 不留下 `.tmp` 残渣（否则用户磁盘上会攒一堆垃圾）。
    """
    write_file(paths, UID, SOUL_FILE, "第一版。")
    write_file(paths, UID, SOUL_FILE, "第二版，长一点的内容。")

    assert read_file(paths, UID, SOUL_FILE) == "第二版，长一点的内容。"
    leftovers = [str(item) for item in Path(paths.data_dir).rglob("*.tmp")]
    assert leftovers == [], f"原子写留下了临时文件：{leftovers}"


def test_persona_section_empty_when_nothing_written(paths):
    # 没用上这两个文件的用户不该多付一个 token
    assert build_persona_section(paths, UID) == ""
    assert build_persona_section(paths, "") == ""


def test_persona_section_includes_both(paths):
    write_file(paths, UID, SOUL_FILE, "温和。")
    write_file(paths, UID, MEMORY_FILE, "用户不喜欢客套。")

    section = build_persona_section(paths, UID)
    assert "温和。" in section
    assert "用户不喜欢客套。" in section


# --------------------------------------------------------------------------- #
# 助手自改（关键：原文过期时必须拒绝，而不是覆盖）
# --------------------------------------------------------------------------- #
def test_self_update_refuses_when_old_text_is_stale():
    """最要紧的一条。

    用户可能刚在设置页手动改过 SOUL.md，而模型手里那份已经过期。
    此时**必须失败**，静默覆盖会吃掉用户的改动且毫无提示。
    """
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
        # 关键断言：原文没被破坏
        assert read_file(paths, UID, SOUL_FILE) == "用户刚手动改过的版本。"


def test_self_update_appends_and_replaces():
    import asyncio

    from my_agent.skill.base import SkillContext
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    with tempfile.TemporaryDirectory() as tmp:
        paths = SimpleNamespace(data_dir=Path(tmp))
        ctx = SkillContext(paths=paths, assistant_id=UID)

        # 追加（old_text 留空）
        asyncio.run(
            SelfPersonaUpdateSkill().run(ctx, file=MEMORY_FILE, old_text="", new_text="记住：别客套。")
        )
        assert "别客套。" in read_file(paths, UID, MEMORY_FILE)

        # 精确替换
        asyncio.run(
            SelfPersonaUpdateSkill().run(
                ctx, file=MEMORY_FILE, old_text="别客套。", new_text="别客套，直接说事。"
            )
        )
        content = read_file(paths, UID, MEMORY_FILE)
        assert "直接说事。" in content
        assert content.count("别客套") == 1


def test_self_update_requires_an_assistant():
    """没绑助手时不能"默认写到某个助手身上" —— 那会写到别人身上且看不出来。"""
    import asyncio

    from my_agent.errors import SkillExecutionError
    from my_agent.skill.base import SkillContext
    from my_agent.skill.builtin.self_persona import SelfPersonaUpdateSkill

    with tempfile.TemporaryDirectory() as tmp:
        ctx = SkillContext(paths=SimpleNamespace(data_dir=Path(tmp)), assistant_id=None)
        with pytest.raises(SkillExecutionError):
            asyncio.run(SelfPersonaUpdateSkill().run(ctx, file=SOUL_FILE, new_text="x"))


# --------------------------------------------------------------------------- #
# 人格锁
# --------------------------------------------------------------------------- #
def test_password_roundtrip_and_no_plaintext_leak():
    profile = AssistantProfile(id="LoveBuddy", name="LoveBuddy")
    assert profile.verify_persona_password("随便什么") is True  # 没上锁 = 不拦

    profile.set_persona_password("1234")
    assert profile.verify_persona_password("1234") is True
    assert profile.verify_persona_password("12345") is False

    payload = profile.to_dict()
    assert "persona_password_hash" not in payload
    assert "persona_password_salt" not in payload
    # 界面只需要知道"有没有锁"
    assert payload["persona_locked"] is True


def test_different_salts_for_same_password():
    """同样的密码两次加盐结果必须不同 —— 否则等于把口令存成了可比对的表。"""
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

    profile.set_persona_password("")  # 重置路径
    assert profile.to_dict()["persona_locked"] is False
    assert profile.verify_persona_password("随便") is True
