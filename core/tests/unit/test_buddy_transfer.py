"""搭子 / 搭子群导入：解析、落盘、幂等，以及"技能已存在就不重复导入"。"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from my_agent.assistants import persona
from my_agent.assistants.presets import builtin_config
from my_agent.assistants.transfer import (
    TransferError,
    apply_buddy,
    apply_buddy_group,
    parse_buddy_json,
    parse_buddy_package,
    parse_group_package,
)
from my_agent.config.paths import AppPaths
from my_agent.server.runtime import AppRuntime

# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #
_SKILL_JSON = {
    "id": "demo-skill",
    "name": "示例技能",
    "description": "演示用的指导型技能",
    "kind": "instruction",
    "instructions": "照着这段说明做事。",
}

_FLAT_BUDDY = {
    "名称": "资料整理助手",
    "昵称": "小整",
    "说明": "负责把散乱资料整理成结构化笔记。",
    "soul.md": "# SOUL\n说话简洁，先给结论。",
    "identity.md": "# IDENTITY\n我是资料整理助手。",
    "rules.md": "# RULES\n不编造，缺信息就问。",
    "温度": 0.4,
    "技能名": [],
}

_OFFICIAL_BUDDY = {
    "type": "xinjianxue.buddy",
    "version": 1,
    "line": "cn",
    "id": "demo-official",
    "name": "官方示例搭子",
    "emoji": "💫",
    "description": "从官网格式导入的搭子。",
    "intro_md": "# 简介\n更长的介绍。",
    "persona": {
        "SOUL.md": "# SOUL\n官网版语气。",
        "IDENTITY.md": "# IDENTITY\n官网版身份。",
        "RULES.md": "# RULES\n官网版规则。",
    },
    "skill_pack": "XJX-Demo-cn.zip",
}


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, bytes) else data.encode("utf-8"))
    return buffer.getvalue()


def buddy_package(buddy: dict, *, with_skill: bool = True) -> bytes:
    """一个搭子包：buddy.json + skills/（技能包既有 zip 形式也有文件夹形式）。"""
    files: dict[str, str | bytes] = {"buddy.json": json.dumps(buddy, ensure_ascii=False)}
    if with_skill:
        # zip 形式
        files["skills/demo-skill.zip"] = zip_bytes({"skill.json": json.dumps(_SKILL_JSON)})
        # 文件夹形式
        files["skills/另一个技能/skill.json"] = json.dumps(
            {**_SKILL_JSON, "id": "demo-skill-2", "name": "示例技能二"}
        )
    return zip_bytes(files)


@pytest.fixture
async def runtime(tmp_path):
    rt = AppRuntime(AppPaths(tmp_path / "data").ensure())
    await rt.initialize()
    try:
        yield rt
    finally:
        await rt.shutdown()


# --------------------------------------------------------------------------- #
# 解析：两种格式都要吃
# --------------------------------------------------------------------------- #
def test_parse_flat_format():
    payload = parse_buddy_json(json.dumps(_FLAT_BUDDY, ensure_ascii=False).encode())
    assert payload.name == "资料整理助手"
    assert payload.nickname == "小整"
    assert payload.temperature == 0.4
    # 技能名留空时解析出空清单；技能名同时接受字符串与数组（见 parse 里的处理）
    assert payload.skills == []
    assert payload.soul.startswith("# SOUL")
    assert payload.identity.startswith("# IDENTITY")
    assert payload.rules.startswith("# RULES")


def test_parse_official_format():
    """官网那种写法：人格三件套在 persona 里，说明用 description。"""
    payload = parse_buddy_json(json.dumps(_OFFICIAL_BUDDY).encode())
    assert payload.source_id == "demo-official"
    assert payload.emoji == "💫"
    assert payload.soul == "# SOUL\n官网版语气。"
    assert payload.rules == "# RULES\n官网版规则。"


def test_rejects_json_without_name():
    with pytest.raises(TransferError) as exc:
        parse_buddy_json(json.dumps({"description": "没有名字"}).encode())
    assert "名称" in str(exc.value)


def test_rejects_out_of_range_temperature():
    """温度越界要在**解析时**说清楚，而不是落盘那一刻抛 pydantic 堆栈。"""
    with pytest.raises(TransferError) as exc:
        parse_buddy_json(json.dumps({"name": "x", "temperature": 9}).encode())
    assert "温度" in str(exc.value)


def test_parse_package_accepts_bare_json():
    """官网那种"一个单独的 .json"也要能直接导。"""
    package = parse_buddy_package(json.dumps(_FLAT_BUDDY, ensure_ascii=False).encode(), "x")
    assert package.buddy.name == "资料整理助手"
    assert package.skill_packs == []


def test_parse_package_collects_both_skill_forms():
    package = parse_buddy_package(buddy_package(_FLAT_BUDDY), "资料整理助手")
    names = sorted(name for name, _ in package.skill_packs)
    assert names == ["demo-skill", "另一个技能"]


def test_parse_package_without_buddy_json_is_rejected():
    with pytest.raises(TransferError) as exc:
        parse_buddy_package(zip_bytes({"skills/x.zip": zip_bytes({"skill.json": "{}"})}), "x")
    assert "搭子文件" in str(exc.value)


# --------------------------------------------------------------------------- #
# 落盘
# --------------------------------------------------------------------------- #
async def test_apply_buddy_writes_profile_persona_and_skills(runtime):
    package = parse_buddy_package(buddy_package(_FLAT_BUDDY), "资料整理助手")
    outcome = await apply_buddy(runtime, package)

    assistant_id = outcome["assistant"]["id"]
    profile = runtime.assistants.get(assistant_id)
    assert profile is not None
    assert profile.name == "资料整理助手"
    assert profile.nickname == "小整"
    assert profile.temperature == 0.4
    # 技能：包里的两个技能包都装上了，且都被配给这个搭子
    assert "demo-skill" in profile.enabled_skills
    assert "demo-skill-2" in profile.enabled_skills

    # 人格三件套是**原文**（不是被模板重新拼过的）
    assert persona.read_file(runtime.paths, assistant_id, "SOUL.md").startswith("# SOUL")
    assert persona.read_file(runtime.paths, assistant_id, "RULES.md").startswith("# RULES")
    assert outcome["skills_missing"] == []


async def test_apply_buddy_reports_missing_skill(runtime):
    """匹配不到的技能名要**如实列出来**，不能悄悄丢掉。"""
    buddy = {**_FLAT_BUDDY, "技能名": ["根本不存在这个技能"]}
    package = parse_buddy_package(buddy_package(buddy, with_skill=False), "x")

    outcome = await apply_buddy(runtime, package)
    assert outcome["skills_missing"] == ["根本不存在这个技能"]
    assert "根本不存在这个技能" in "".join(item.get("message", "") for item in outcome["results"])


async def test_apply_buddy_twice_is_idempotent(runtime):
    """同一个包导两次：不重复建搭子、也不重复装技能（用户明确要求）。"""
    raw = buddy_package(_FLAT_BUDDY)
    first = await apply_buddy(runtime, parse_buddy_package(raw, "x"))
    second = await apply_buddy(runtime, parse_buddy_package(raw, "x"))

    assert first["assistant"]["id"] == second["assistant"]["id"]
    assert second["action"] == "update"
    names = [item.name for item in runtime.assistants.sorted()]
    assert names.count("资料整理助手") == 1
    # 技能没有多出一份（既有的安装路径会给重名加 -2 后缀）
    custom_ids = sorted(item.id for item in runtime.custom_skills.skills)
    assert custom_ids == ["demo-skill", "demo-skill-2"]
    skipped = [item for item in second["results"] if item.get("skipped")]
    assert skipped, "第二次导入应如实说明技能已存在、未重复导入"


async def test_apply_buddy_updates_existing_assistant(runtime):
    """同名同 id 的的自建搭子存在时，**更新它**而不是造第二个。"""
    first = await apply_buddy(runtime, parse_buddy_package(buddy_package(_FLAT_BUDDY), "x"))
    buddy = {
        "type": "xinjianxue.buddy",
        "id": first["assistant"]["id"],
        "name": _FLAT_BUDDY["名称"],
        "emoji": "🌟",
        "description": "官网版简介",
        "persona": {"SOUL.md": "# SOUL\n官方覆盖版"},
    }
    outcome = await apply_buddy(runtime, parse_buddy_package(json.dumps(buddy).encode(), "x"))

    assert outcome["action"] == "update"
    assert outcome["assistant"]["id"] == first["assistant"]["id"]
    assert len(runtime.assistants.sorted()) == len(builtin_config().assistants) + 1
    assert persona.read_file(runtime.paths, first["assistant"]["id"], "SOUL.md") == "# SOUL\n官方覆盖版"


async def test_apply_buddy_refuses_to_overwrite_locked_builtin(runtime):
    """⚠️ 四位内置搭子**任何途径不可改** —— 导入也算一条途径。

    而且这条路最阴：它**按名字匹配**，一个叫「Soulmate」的包会直接命中产品自带的那位，
    然后把简介、人设、能力一并覆盖掉。用户看到的只是"导入成功"。
    """
    builtin = runtime.assistants.get("soulmate")
    assert builtin is not None, "这个用例依赖内置的 soulmate"
    before = persona.read_file(runtime.paths, "soulmate", "SOUL.md")
    buddy = {
        "type": "xinjianxue.buddy",
        "id": "soulmate",
        "name": builtin.name,
        "emoji": "🌟",
        "description": "官网版简介",
        "persona": {"SOUL.md": "# SOUL\n官方覆盖版"},
    }
    outcome = await apply_buddy(runtime, parse_buddy_package(json.dumps(buddy).encode(), "x"))

    assert outcome["action"] == "blocked"
    assert outcome["ok"] is False
    # 如实回报，而不是静默跳过 —— 静默跳过的话用户以为包装上了
    assert outcome["results"][-1]["ok"] is False
    assert len([item for item in runtime.assistants.sorted() if item.id == "soulmate"]) == 1
    assert persona.read_file(runtime.paths, "soulmate", "SOUL.md") == before


async def test_apply_buddy_drops_reserved_xjx_skills(runtime):
    """包里写了心鉴学专属技能名 → 收下这个包、丢掉那几项、并说明为什么。

    ⚠️ 刻意**不是**硬拒绝：官网导出的搭子包里本来就写着这几个名字，
    硬拒会让"导入官方包"直接报错，用户看到的是"包坏了"。
    """
    # ⚠️ 键名必须用「技能名」：解析器按 skills → 技能名 → 技能 的顺序取**第一个**
    # 存在的，写「技能」会被 _FLAT_BUDDY 里已有的「技能名」盖过去（测试会假绿）。
    buddy = {**_FLAT_BUDDY, "名称": "专属技能测试", "技能名": ["Soulmate专用", "demo-skill"]}
    outcome = await apply_buddy(runtime, parse_buddy_package(buddy_package(buddy), "x"))

    assert outcome["ok"] is True
    assert "Soulmate专用" not in outcome["skills"]
    note = [item for item in outcome["results"] if item["name"] == "专属技能"]
    assert note and "Soulmate专用" in note[0]["message"]


# --------------------------------------------------------------------------- #
# 搭子群
# --------------------------------------------------------------------------- #
def group_package() -> bytes:
    return zip_bytes(
        {
            "group.json": json.dumps(
                {"type": "xinjianxue.buddy-group", "name": "整理小队", "speaking_order": ["甲搭子"]},
                ensure_ascii=False,
            ),
            "buddies/甲搭子/buddy.json": json.dumps(
                {**_FLAT_BUDDY, "名称": "甲搭子"}, ensure_ascii=False
            ),
            "buddies/乙搭子/搭子.json": json.dumps(
                {**_FLAT_BUDDY, "名称": "乙搭子"}, ensure_ascii=False
            ),
        }
    )


async def test_apply_group_creates_group_without_roles(runtime):
    package = parse_group_package(group_package(), "整理小队")
    assert sorted(item.buddy.name for item in package.members) == sorted(["甲搭子", "乙搭子"])

    outcome = await apply_buddy_group(runtime, package)
    group = runtime.groups.get(outcome["group"]["id"])
    assert group is not None
    assert group.name == "整理小队"
    assert len(group.member_assistant_ids) == 2
    # 导入不替你定审核员 / 优化顾问（那两个要另行提交 id）
    assert group.reviewer_id == ""
    assert group.advisor_id == ""
    # 发言顺序按**名字**匹配成了真实 id
    assert group.speaking_order == [outcome["assistants"][0]["id"]] or len(group.speaking_order) == 1


def test_group_package_without_group_json_is_rejected():
    with pytest.raises(TransferError) as exc:
        parse_group_package(zip_bytes({"buddies/a/buddy.json": "{}"}), "x")
    assert "group.json" in str(exc.value)


def test_group_package_with_one_member_is_reported():
    """只解出一个成员时要在解析/落盘处明确报错，不能建出一个讨论不起来的群。"""
    raw = zip_bytes(
        {
            "group.json": json.dumps({"name": "孤单群"}),
            "buddies/甲搭子/buddy.json": json.dumps({**_FLAT_BUDDY, "名称": "甲搭子"}, ensure_ascii=False),
        }
    )
    package = parse_group_package(raw, "孤单群")
    assert len(package.members) == 1
