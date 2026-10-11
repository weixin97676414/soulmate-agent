"""搭子包导入：**技能名匹配口径** + 随包技能真正配上 + 被关技能自动打开。

对应 2026-09-28 用户实测反馈的问题（截图为证）：

```
⚠️ 这些技能在本机找不到，已跳过：xinjianxue-skill-self_qa-global、…
✔ xinjianxue-skill-self_qa-global   已存在，未重复导入
✘ 技能清单   已配置 3 个技能，未找到: xinjianxue-skill-self_qa-global, …
```

同一个技能一边打绿勾、一边进「未找到」清单。

**根因不在文案，在匹配口径**：指导型技能（``kind="instruction"``，即技能包里
只有 SKILL.md 的那一类）**不会被注册进 SkillManager** ——
``custom.sync_custom_skills`` 有意跳过它们（它不执行任何动作，注册了只会让模型
看到一个"调了也没意义"的工具）。而 ``_resolve_skills`` 原先只查 manager 里的
工具名，于是这类技能**永远匹配不到**；同一个技能在 ``_skill_already_here``
那边（查 ``custom_skills.skills``）却被判成"已存在"。

所以这一组用例盯的是"**判已有**"与"**解析名字**"两条路必须同口径，而不是
"提示文案改得好看点"。
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from my_agent.assistants.transfer import apply_buddy, parse_buddy_package
from my_agent.config.paths import AppPaths
from my_agent.config.schemas import CustomSkillDef
from my_agent.server.runtime import AppRuntime
from my_agent.skill.install import install_defs

# 用户实测里出现的那个名字（带下划线与短横线）。刻意用**真实那一个**而不是自造，
# 免得"名字形态特殊"这一类因素被测试绕过。
GUIDE_ID = "xinjianxue-skill-self_qa-global"


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buffer.getvalue()


def guide_def(*, skill_id: str = GUIDE_ID, enabled: bool = True) -> CustomSkillDef:
    """一个指导型技能定义（技能包里只有 SKILL.md 时就是这个形态）。"""
    return CustomSkillDef(
        id=skill_id,
        name=skill_id,
        description="随包带的指导型技能",
        kind="instruction",
        instructions="照这段说明做事。",
        enabled=enabled,
    )


def buddy_zip(skills: list[str], *, extra: dict[str, str | bytes] | None = None) -> bytes:
    """一个搭子包：buddy.json（技能名指向 skills）+ 可选的技能包。"""
    files: dict[str, str | bytes] = {
        "buddy.json": json.dumps(
            {
                "名称": "岸",
                "昵称": "岸",
                "说明": "从包里导入的搭子。",
                "soul.md": "# SOUL\n先行一步。",
                "技能名": skills,
            },
            ensure_ascii=False,
        )
    }
    files.update(extra or {})
    return zip_bytes(files)


def guide_pack_zip(skill_id: str = GUIDE_ID) -> bytes:
    """一个只含 skill.json 的指导型技能包（会被 ``_collect_skill_packs`` 收进来）。"""
    return zip_bytes(
        {"skill.json": json.dumps({**guide_def(skill_id=skill_id).model_dump(), "enabled": True})}
    )


@pytest.fixture
async def runtime(tmp_path):
    rt = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await rt.initialize()
    try:
        yield rt
    finally:
        await rt.shutdown()


def install(runtime: AppRuntime, defs: list[CustomSkillDef]) -> None:
    """走生产那条安装路径（含校验与重载），别在测试里自己拼配置。"""
    install_defs(runtime, defs, [])


# --------------------------------------------------------------------------- #
# 匹配口径：指导型技能也必须能被"技能名"指到
# --------------------------------------------------------------------------- #
async def test_guide_skill_is_not_reported_missing(runtime):
    """已装好的**指导型**技能被搭子包点名 → 不能报「未找到」。"""
    install(runtime, [guide_def()])
    # 前提校验：这类技能确实不在 manager 的工具表里。
    # 少了这一条，哪天它被注册成工具了，本用例会变成"测了个寂寞"。
    assert GUIDE_ID not in runtime.skills.all_names()

    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "buddy-an-global.zip")
    )

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]
    # 真正配上才算数：白名单（``enabled_skills``）是运行时唯一的依据
    profile = runtime.assistants.get(outcome["assistant"]["id"])
    assert GUIDE_ID in profile.enabled_skills


async def test_guide_skill_name_is_not_reported_twice(runtime):
    """同一条技能**不能一边"已存在"一边"未找到"**（用户截图里的自相矛盾）。

    要复现用户那个场景，包里必须**真的带技能包** —— "已存在，未重复导入"
    那条绿勾来自技能包的安装路径，而用户看到的红叉来自搭子 json 的技能名解析。
    两边都指向同一个技能时，才谈得上"自相矛盾"。
    """
    install(runtime, [guide_def()])

    payload = buddy_zip([GUIDE_ID], extra={"skills/x.zip": guide_pack_zip()})
    outcome = await apply_buddy(runtime, parse_buddy_package(payload, "p.zip"))

    mentioned = [
        item for item in outcome["results"] if GUIDE_ID in json.dumps(item, ensure_ascii=False)
    ]
    assert mentioned, "至少要有一条关于这个技能的回报"
    assert outcome["skills_missing"] == []
    # 提到这个技能的每一条都必须 ok —— 一条绿一条红就是用户截图里那个 bug
    assert all(item.get("ok") for item in mentioned), mentioned


async def test_missing_skill_still_reported(runtime):
    """放宽匹配**不等于**什么都算命中：真没有的仍要如实报出。"""
    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip(["no-such-skill"]), "p.zip")
    )
    assert outcome["skills_missing"] == ["no-such-skill"]


async def test_skill_name_with_trailing_space_still_matches(runtime):
    """包里手写的 json 常带尾空格 —— 界面上看不出来，但会变成"未找到"。"""
    install(runtime, [guide_def()])

    outcome = await apply_buddy(
        runtime, parse_buddy_package(buddy_zip([f"{GUIDE_ID} "]), "p.zip")
    )

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]


# --------------------------------------------------------------------------- #
# 随包技能：装上、配给搭子、并且**被关掉的要自动打开**
# --------------------------------------------------------------------------- #
async def test_pack_guide_skill_is_installed_and_configured(runtime):
    """随包带进来的指导型技能：算"装上了"，也要配给这个搭子。"""
    payload = buddy_zip([GUIDE_ID], extra={"skills/x.zip": guide_pack_zip()})
    outcome = await apply_buddy(runtime, parse_buddy_package(payload, "p.zip"))

    assert outcome["skills_missing"] == []
    assert GUIDE_ID in outcome["skills"]
    assert GUIDE_ID in runtime.assistants.get(outcome["assistant"]["id"]).enabled_skills


async def test_disabled_skill_used_by_pack_is_opened(runtime):
    """本机已有但被全局关掉 → 按用户口径**自动打开**，并在结果里说明。

    口径来源：2026-09-28 用户选择「配给新搭子并自动打开」。理由很直接 ——
    他导入这个包的意图就是让这个搭子能干这些事，而关着的技能
    在 ``collect_instructions`` 里会被直接跳过，界面上**一句提示都不会有**。
    """
    install(runtime, [guide_def(enabled=False)])
    assert runtime.custom_skills.get(GUIDE_ID).enabled is False

    outcome = await apply_buddy(runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "p.zip"))

    assert runtime.custom_skills.get(GUIDE_ID).enabled is True
    assert any(
        "自动打开" in (item.get("message") or "") for item in outcome["results"]
    ), "打开了就要说，不能悄悄改配置"


async def test_only_used_skills_are_opened(runtime):
    """只打开**这次真正要用到**的：把用户自己关掉、与本次无关的技能一并打开是另一件事。"""
    other = "some-other-skill"
    install(runtime, [guide_def(enabled=False), guide_def(skill_id=other, enabled=False)])

    await apply_buddy(runtime, parse_buddy_package(buddy_zip([GUIDE_ID]), "p.zip"))

    assert runtime.custom_skills.get(GUIDE_ID).enabled is True
    assert runtime.custom_skills.get(other).enabled is False, "无关技能不该被动到"
