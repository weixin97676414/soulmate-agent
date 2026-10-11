"""心鉴学专属技能：归属表、按线路二选一、以及"关不掉"的判定依据。

## 这四个技能是什么

它们是**指导型**技能：内容是一份 SKILL.md（怎么取报告、怎么核对地点、怎么解读），
由 ``skill/custom.py::persona_with_instructions`` 注入 system 提示词，
模型据此调用核心内置的两个工具（``skill/builtin/geo_lookup.py`` 与
``skill/builtin/xjx_report.py``）。它们**不是工具**，所以不进 ``SkillManager``
的注册表 —— 注册了就会被当成一个"调了也没用"的工具暴露给模型。

正文原文落在 ``my_agent/resources/xjx/*.md``（随核心打包，见
``core/build/agent-core.spec`` 的 datas 与 ``utils/resources.py``）。

## 四条硬约束（产品约定）

1. **按线路二选一**：``cn`` 线路只启用 ``*-cn``，``seoul`` 线路只启用
   ``*-global``。不是"两个都装、用户挑一个"，而是"同一时刻只有一个存在"——
   ``active_skills()`` 是唯一入口，别在别处按名字拼。
2. **默认开启、无开关、关不掉**：启用状态**不落盘、无字段**，是线路的纯函数
   —— 没有可改的状态，也就无从关起。想改的人只剩"直接改代码"这一条路，
   而不是"某个接口忘了拦"。
3. **按归属搭子隔离**：``Soulmate专用`` 只给 ``soulmate``；``人际关系运营``
   只给 ``LoveBuddy`` / ``RelationBuddy``。判定集中在本模块，且**在会话/群聊/
   定时任务三条组装路径上都要过一遍**（工具清单走
   ``SkillManager.to_tool_specs(for_assistant=...)``，正文注入走
   ``persona_with_instructions``），一条路径漏了就等于该搭子能看见别人的专属技能。
4. **非归属搭子不可添加**：搭子档案里的 ``enabled_skills`` 白名单**不允许**
   写入这些名字（见 ``agent/orchestrator.py`` 与 ``server/routes/assistants.py``）。
   它们本来就不是工具，写进白名单只会把该搭子的工具清单收敛成"什么都没有"。

## 与 ``skill/locked.py`` 的关系

配套的两个工具名进了 ``ALWAYS_ON_SKILLS``（关不掉、免批准），但**不进技能设置页**
（见 ``server/routes/skills.py`` 的 ``HIDDEN_SKILLS``）—— 用户该看到的是
「Soulmate专用」和「人际关系运营」两张卡，而不是实现它们的螺丝。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...utils.resources import read_text

# --------------------------------------------------------------------------- #
# 线路与分组
# --------------------------------------------------------------------------- #
LINE_CN = "cn"
LINE_SEOUL = "seoul"

GROUP_SOULMATE = "soulmate"
GROUP_BUDDIES = "buddies"

# 搭子在界面上的叫法（只用于给用户看的说明文案，不参与任何判定）
OWNER_LABELS: dict[str, str] = {
    "soulmate": "Soulmate",
    "LoveBuddy": "Love Buddy",
    "RelationBuddy": "Relation Buddy",
}

# 心鉴学服务端的两个报表端点（``POST {report_base}/api/buddy/v1/{path}``）
REPORT_PATHS: dict[str, str] = {
    GROUP_SOULMATE: "soulmate/report",
    GROUP_BUDDIES: "buddies/report",
}

# 配套工具名（真 Skill，注册进 SkillManager）
TOOL_PLACE_LOOKUP = "xjx_place_lookup"
TOOL_FETCH_REPORT = "xjx_fetch_report"
XJX_TOOL_NAMES: frozenset[str] = frozenset({TOOL_PLACE_LOOKUP, TOOL_FETCH_REPORT})

# 这两个工具在界面上的显示名。**必须单独列一份**：拒绝文案的调用点
# （``skill/manager.py`` 的 set_enabled / set_permission）传进来的是
# ``meta.display_name`` 而不是技能 id，只认 id 的话这类拒绝会走到通用文案，
# 用户看到「它承载搭子的长期记忆」——而那和取报告毫无关系。
XJX_TOOL_LABELS: frozenset[str] = frozenset({"地点核对", "报告代取"})


@dataclass(frozen=True)
class XjxSkill:
    """一个内置专属技能。``name`` 是内部 id（也用于占名），``display_name`` 给用户看。"""

    name: str
    display_name: str
    group: str
    line: str
    owners: tuple[str, ...]
    resource: str
    summary: str

    @property
    def report_path(self) -> str:
        return REPORT_PATHS[self.group]

    @property
    def owner_label(self) -> str:
        return "、".join(OWNER_LABELS.get(item, item) for item in self.owners)


# 四个技能。中文名按用户口径**统一**：cn 与 global 同名，靠线路区分 ——
# 界面上同一时刻只会出现其中一个（见 active_skills），所以不会出现同名两张卡。
XJX_SKILLS: tuple[XjxSkill, ...] = (
    XjxSkill(
        name="xjx-soulmate-cn",
        display_name="Soulmate专用",
        group=GROUP_SOULMATE,
        line=LINE_CN,
        owners=("soulmate",),
        resource="soulmate-cn.md",
        summary="取回用户本人的心鉴学报告并落到搭子文件（大陆站）。",
    ),
    XjxSkill(
        name="xjx-soulmate-global",
        display_name="Soulmate专用",
        group=GROUP_SOULMATE,
        line=LINE_SEOUL,
        owners=("soulmate",),
        resource="soulmate-global.md",
        summary="取回用户本人的心鉴学报告并落到搭子文件（国际站）。",
    ),
    XjxSkill(
        name="xjx-buddies-cn",
        display_name="人际关系运营",
        group=GROUP_BUDDIES,
        line=LINE_CN,
        owners=("LoveBuddy", "RelationBuddy"),
        resource="buddies-cn.md",
        summary="取回用户的人际关系报告并落成可执行的相处建议（大陆站）。",
    ),
    XjxSkill(
        name="xjx-buddies-global",
        display_name="人际关系运营",
        group=GROUP_BUDDIES,
        line=LINE_SEOUL,
        owners=("LoveBuddy", "RelationBuddy"),
        resource="buddies-global.md",
        summary="取回用户的人际关系报告并落成可执行的相处建议（国际站）。",
    ),
)

XJX_SKILL_NAMES: frozenset[str] = frozenset(item.name for item in XJX_SKILLS)

# 占名清单：内部 id + 中文显示名。任何"新建自定义技能"都不允许撞上它们 ——
# 否则用户会看到两张同名的卡，而其中一张能删、另一张关不掉。
XJX_RESERVED_NAMES: frozenset[str] = XJX_SKILL_NAMES | frozenset(
    item.display_name for item in XJX_SKILLS
)

_BY_NAME: dict[str, XjxSkill] = {item.name: item for item in XJX_SKILLS}

# 全部归属搭子（两个组并起来）—— 决定谁有权调用那两个配套工具
XJX_OWNER_IDS: frozenset[str] = frozenset(
    owner for item in XJX_SKILLS for owner in item.owners
)


# --------------------------------------------------------------------------- #
# 判定
# --------------------------------------------------------------------------- #
def is_xjx_skill(name: str) -> bool:
    """是那四个内置专属技能之一（不是配套工具）。"""
    return name in XJX_SKILL_NAMES


def is_xjx_tool(name: str) -> bool:
    """是心鉴学的配套工具（``xjx_place_lookup`` / ``xjx_fetch_report``）。"""
    return name in XJX_TOOL_NAMES


def is_reserved(name: str) -> bool:
    """名字被心鉴学占掉了（技能 id、显示名、工具名或工具显示名）。"""
    return (
        name in XJX_RESERVED_NAMES
        or name in XJX_TOOL_NAMES
        or name in XJX_TOOL_LABELS
    )


def skill_by_name(name: str) -> XjxSkill | None:
    return _BY_NAME.get(name)


def is_owner(assistant_id: str | None, skill: XjxSkill) -> bool:
    return bool(assistant_id) and assistant_id in skill.owners


def active_skills(line: str | None) -> tuple[XjxSkill, ...]:
    """当前线路下**存在**的两个技能（其它线路的两个技能视为不存在）。"""
    target = line or LINE_CN
    if target not in (LINE_CN, LINE_SEOUL):
        target = LINE_CN
    return tuple(item for item in XJX_SKILLS if item.line == target)


def skills_for_assistant(assistant_id: str | None, line: str | None) -> tuple[XjxSkill, ...]:
    """这个搭子在当前线路下可用的专属技能（通常是 0 或 1 个）。"""
    if not assistant_id:
        return ()
    return tuple(item for item in active_skills(line) if assistant_id in item.owners)


def group_for_assistant(assistant_id: str | None, line: str | None) -> str | None:
    """该搭子在本线路上归属的分组（``soulmate`` / ``buddies``），没有则 ``None``。

    报告端点是**按搭子**定的，不是按模型传的参数定的 —— 否则 Love Buddy
    传一句 ``report="soulmate"`` 就能去取 Soulmate 的报表。
    """
    skills = skills_for_assistant(assistant_id, line)
    return skills[0].group if skills else None


def may_use_tools(assistant_id: str | None) -> bool:
    """这个搭子能不能看见/调用心鉴学的两个配套工具。"""
    return bool(assistant_id) and assistant_id in XJX_OWNER_IDS


def forbidden_tool_names(assistant_id: str | None) -> frozenset[str]:
    """该搭子**不该看见**的技能名（工具）。

    非归属搭子连工具都不该出现在清单里 —— 只在执行时报错，模型会先看见一个
    多余的工具，还会忍不住去调（"看得见=可用"是模型的默认理解）。
    """
    if may_use_tools(assistant_id):
        return frozenset()
    return XJX_TOOL_NAMES


# --------------------------------------------------------------------------- #
# 正文
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=8)
def instructions(name: str) -> str:
    """读某个技能的 SKILL.md 原文（带缓存：注入提示词是每次请求都要走的路）。"""
    skill = _BY_NAME.get(name)
    if skill is None:
        raise KeyError(f"不是心鉴学内置技能：{name}")
    return read_text("xjx", skill.resource)


def skill_document(name: str) -> str:
    """``instructions`` 的别名，语义更直白一些（给调用点读起来顺）。"""
    return instructions(name)


def describe(skill: XjxSkill) -> dict[str, Any]:
    """给技能设置页用的条目（形状对齐 ``SkillMeta.to_dict()``）。

    ``locked`` 与 ``source`` 让界面**不画开关**并把来源标成内置；
    ``owners`` / ``line`` / ``auto`` 是心鉴学独有的附加说明字段，
    老前端忽略它们也不会出错。
    """
    from .. import groups  # 函数内导入：groups 会回头 import 本模块（见它的文件头说明）

    return {
        "name": skill.name,
        "display_name": skill.display_name,
        "description": skill.summary,
        "parameters": {"type": "object", "properties": {}},
        "category": "persona",
        "permission_level": "safe",
        "timeout": 0.0,
        "enabled": True,
        "tags": ["心鉴学", f"线路:{skill.line}", f"归属:{skill.owners[0]}"],
        "source": "builtin",
        # 四分类：心鉴学这两条是各内置搭子的**专属技能**（产品约定）
        "bucket": groups.BUCKET_EXCLUSIVE,
        "locked": True,
        # ---- 附加说明 ----
        "instruction_only": True,
        "line": skill.line,
        "owners": list(skill.owners),
        "owner_label": skill.owner_label,
        "auto_enabled": True,
        "locked_reason": (
            f"「{skill.display_name}」是 {skill.owner_label} 的专属能力："
            "按当前线路自动启用，不提供开关，也不能修改。"
        ),
    }


def reject_reserved_skill_names(names: Iterable[str]) -> None:
    """一份 ``enabled_skills`` 白名单里混进心鉴学专属技能名时，抛 ``ValueError``。

    **为什么是拒绝而不是静默剔除**（"非归属搭子不可添加"）：

    1. 它们不是"可有可无的附加项"，而是**按线路 + 归属自动生效**的能力 ——
       写进白名单一点用都没有，真正生效与否只取决于当前线路与这个搭子是谁；
    2. 更糟的是**用户会以为"加上了"**：专属技能按"线路 + 归属"自动生效，
       ``enabled_skills`` 的含义只是"额外勾选了哪些通用 / 我的技能"
       （2026-10-06 口径，见 ``skill/groups.py``）—— 写进去既不生效、
       又让这份清单看起来"我已经把它加上了"。

    所以这里明确报错，并告诉模型"这是自动的，别写"。
    """
    bad = sorted({item for item in names if is_reserved(item)})
    if not bad:
        return
    raise ValueError(
        f"「{'、'.join(bad)}」是内置专属技能：按当前线路自动启用、只属于对应的搭子，"
        "**不能写进技能清单** —— 写进去不会生效，还会把这个搭子的其它技能挤掉。"
        "专属技能不需要（也不允许）手动添加。"
    )


def locked_message(name: str) -> str:
    """给用户/调用方看的一句拒绝理由（按名字自适应，id 与显示名都认）。"""
    skill = _BY_NAME.get(name)
    if skill is not None:
        return (
            f"「{skill.display_name}」是 {skill.owner_label} 的内置专属技能："
            "按当前线路自动启用，不提供开关，也不能修改或删除。"
        )
    if name in XJX_TOOL_NAMES or name in XJX_TOOL_LABELS:
        return (
            "「地点核对 / 报告代取」是心鉴学专属技能的配套工具："
            "默认开启、免批准，不提供开关。"
        )
    return f"「{name}」是心鉴学内置技能，不提供开关。"


__all__ = [
    "GROUP_BUDDIES",
    "GROUP_SOULMATE",
    "LINE_CN",
    "LINE_SEOUL",
    "OWNER_LABELS",
    "REPORT_PATHS",
    "TOOL_FETCH_REPORT",
    "TOOL_PLACE_LOOKUP",
    "XJX_TOOL_LABELS",
    "XJX_OWNER_IDS",
    "XJX_RESERVED_NAMES",
    "XJX_SKILLS",
    "XJX_SKILL_NAMES",
    "XJX_TOOL_NAMES",
    "XjxSkill",
    "active_skills",
    "describe",
    "forbidden_tool_names",
    "group_for_assistant",
    "instructions",
    "is_owner",
    "is_reserved",
    "is_xjx_skill",
    "is_xjx_tool",
    "locked_message",
    "may_use_tools",
    "reject_reserved_skill_names",
    "skill_by_name",
    "skill_document",
    "skills_for_assistant",
]
