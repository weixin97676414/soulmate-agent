




































from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ...utils.resources import read_text




LINE_CN = "cn"
LINE_SEOUL = "seoul"

GROUP_SOULMATE = "soulmate"
GROUP_BUDDIES = "buddies"

GROUP_ASTRO = "astro"
GROUP_BAZI = "bazi"
GROUP_MEIHUA = "meihua"
GROUP_TAROT = "tarot"


OWNER_LABELS: dict[str, str] = {
    "soulmate": "Soulmate",
    "LoveBuddy": "Love Buddy",
    "RelationBuddy": "Relation Buddy",
    "FortuneTellingBuddy": "Fortune telling Buddy",
}


REPORT_PATHS: dict[str, str] = {
    GROUP_SOULMATE: "soulmate/report",
    GROUP_BUDDIES: "buddies/report",
}


TOOL_PLACE_LOOKUP = "xjx_place_lookup"
TOOL_FETCH_REPORT = "xjx_fetch_report"

TOOL_FETCH_ASTRO = "xjx_fetch_astro"
TOOL_FETCH_BAZI = "xjx_fetch_bazi"
TOOL_FETCH_MEIHUA = "xjx_fetch_meihua"
TOOL_FETCH_TAROT = "xjx_fetch_tarot"
XJX_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_PLACE_LOOKUP,
        TOOL_FETCH_REPORT,
        TOOL_FETCH_ASTRO,
        TOOL_FETCH_BAZI,
        TOOL_FETCH_MEIHUA,
        TOOL_FETCH_TAROT,
    }
)





TOOL_OWNERS: dict[str, tuple[str, ...]] = {
    TOOL_PLACE_LOOKUP: ("soulmate", "LoveBuddy", "RelationBuddy", "FortuneTellingBuddy"),
    TOOL_FETCH_REPORT: ("soulmate", "LoveBuddy", "RelationBuddy"),
    TOOL_FETCH_ASTRO: ("FortuneTellingBuddy",),
    TOOL_FETCH_BAZI: ("FortuneTellingBuddy",),
    TOOL_FETCH_MEIHUA: ("FortuneTellingBuddy",),
    TOOL_FETCH_TAROT: ("FortuneTellingBuddy",),
}





TOOL_DISPLAY: dict[str, str] = {
    TOOL_PLACE_LOOKUP: "地点核对",
    TOOL_FETCH_REPORT: "报告代取",
    TOOL_FETCH_ASTRO: "西占取盘",
    TOOL_FETCH_BAZI: "八字排盘",
    TOOL_FETCH_MEIHUA: "梅花起卦",
    TOOL_FETCH_TAROT: "塔罗洗牌",
}
XJX_TOOL_LABELS: frozenset[str] = frozenset(TOOL_DISPLAY.values())


@dataclass(frozen=True)
class XjxSkill:







    name: str
    display_name: str
    group: str
    line: str
    owners: tuple[str, ...]
    resource: str
    tool: str
    summary: str

    @property
    def report_path(self) -> str:
        return REPORT_PATHS[self.group]

    @property
    def owner_label(self) -> str:
        return "、".join(OWNER_LABELS.get(item, item) for item in self.owners)







XJX_SKILLS: tuple[XjxSkill, ...] = (
    XjxSkill(
        name="xjx-soulmate-cn",
        display_name="Soulmate专用",
        group=GROUP_SOULMATE,
        line=LINE_CN,
        owners=("soulmate",),
        resource="soulmate-cn.md",
        tool=TOOL_FETCH_REPORT,
        summary="取回用户本人的心鉴学报告并落到搭子文件（大陆站）。",
    ),
    XjxSkill(
        name="xjx-soulmate-global",
        display_name="Soulmate专用",
        group=GROUP_SOULMATE,
        line=LINE_SEOUL,
        owners=("soulmate",),
        resource="soulmate-global.md",
        tool=TOOL_FETCH_REPORT,
        summary="取回用户本人的心鉴学报告并落到搭子文件（国际站）。",
    ),
    XjxSkill(
        name="xjx-buddies-cn",
        display_name="人际关系运营",
        group=GROUP_BUDDIES,
        line=LINE_CN,
        owners=("LoveBuddy", "RelationBuddy"),
        resource="buddies-cn.md",
        tool=TOOL_FETCH_REPORT,
        summary="取回用户的人际关系报告并落成可执行的相处建议（大陆站）。",
    ),
    XjxSkill(
        name="xjx-buddies-global",
        display_name="人际关系运营",
        group=GROUP_BUDDIES,
        line=LINE_SEOUL,
        owners=("LoveBuddy", "RelationBuddy"),
        resource="buddies-global.md",
        tool=TOOL_FETCH_REPORT,
        summary="取回用户的人际关系报告并落成可执行的相处建议（国际站）。",
    ),
    
    XjxSkill(
        name="xjx-astro-cn",
        display_name="西占",
        group=GROUP_ASTRO,
        line=LINE_CN,
        owners=("FortuneTellingBuddy",),
        resource="astro-cn.md",
        tool=TOOL_FETCH_ASTRO,
        summary="取回本命盘或行运盘并按提示词解读（大陆站）。",
    ),
    XjxSkill(
        name="xjx-astro-global",
        display_name="西占",
        group=GROUP_ASTRO,
        line=LINE_SEOUL,
        owners=("FortuneTellingBuddy",),
        resource="astro-global.md",
        tool=TOOL_FETCH_ASTRO,
        summary="取回本命盘或行运盘并按提示词解读（国际站）。",
    ),
    
    XjxSkill(
        name="xjx-bazi-cn",
        display_name="八字",
        group=GROUP_BAZI,
        line=LINE_CN,
        owners=("FortuneTellingBuddy",),
        resource="bazi-cn.md",
        tool=TOOL_FETCH_BAZI,
        summary="排八字命盘（原局 / 大运 / 流年）并按提示词解读（大陆站）。",
    ),
    XjxSkill(
        name="xjx-bazi-global",
        display_name="八字",
        group=GROUP_BAZI,
        line=LINE_SEOUL,
        owners=("FortuneTellingBuddy",),
        resource="bazi-global.md",
        tool=TOOL_FETCH_BAZI,
        summary="排八字命盘（原局 / 大运 / 流年）并按提示词解读（国际站）。",
    ),
    
    XjxSkill(
        name="xjx-meihua-cn",
        display_name="梅花易数",
        group=GROUP_MEIHUA,
        line=LINE_CN,
        owners=("FortuneTellingBuddy",),
        resource="meihua-cn.md",
        tool=TOOL_FETCH_MEIHUA,
        summary="按用户自报两数起卦并按体用规则断卦（大陆站）。",
    ),
    XjxSkill(
        name="xjx-meihua-global",
        display_name="梅花易数",
        group=GROUP_MEIHUA,
        line=LINE_SEOUL,
        owners=("FortuneTellingBuddy",),
        resource="meihua-global.md",
        tool=TOOL_FETCH_MEIHUA,
        summary="按用户自报两数起卦并按体用规则断卦（国际站）。",
    ),
    
    XjxSkill(
        name="xjx-tarot-cn",
        display_name="塔罗",
        group=GROUP_TAROT,
        line=LINE_CN,
        owners=("FortuneTellingBuddy",),
        resource="tarot-cn.md",
        tool=TOOL_FETCH_TAROT,
        summary="洗牌 / 切牌后按牌阵逐张解读（大陆站）。",
    ),
    XjxSkill(
        name="xjx-tarot-global",
        display_name="塔罗",
        group=GROUP_TAROT,
        line=LINE_SEOUL,
        owners=("FortuneTellingBuddy",),
        resource="tarot-global.md",
        tool=TOOL_FETCH_TAROT,
        summary="洗牌 / 切牌后按牌阵逐张解读（国际站）。",
    ),
)

XJX_SKILL_NAMES: frozenset[str] = frozenset(item.name for item in XJX_SKILLS)



XJX_RESERVED_NAMES: frozenset[str] = XJX_SKILL_NAMES | frozenset(
    item.display_name for item in XJX_SKILLS
)

_BY_NAME: dict[str, XjxSkill] = {item.name: item for item in XJX_SKILLS}


XJX_OWNER_IDS: frozenset[str] = frozenset(
    owner for item in XJX_SKILLS for owner in item.owners
)





def is_xjx_skill(name: str) -> bool:

    return name in XJX_SKILL_NAMES


def is_xjx_tool(name: str) -> bool:

    return name in XJX_TOOL_NAMES


def is_reserved(name: str) -> bool:

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

    target = line or LINE_CN
    if target not in (LINE_CN, LINE_SEOUL):
        target = LINE_CN
    return tuple(item for item in XJX_SKILLS if item.line == target)


def skills_for_assistant(assistant_id: str | None, line: str | None) -> tuple[XjxSkill, ...]:

    if not assistant_id:
        return ()
    return tuple(item for item in active_skills(line) if assistant_id in item.owners)


def group_for_assistant(assistant_id: str | None, line: str | None) -> str | None:








    for item in skills_for_assistant(assistant_id, line):
        if item.tool == TOOL_FETCH_REPORT:
            return item.group
    return None


def tool_owners(tool: str) -> tuple[str, ...]:

    return TOOL_OWNERS.get(tool, ())


def may_use_tool(assistant_id: str | None, tool: str) -> bool:





    return bool(assistant_id) and assistant_id in TOOL_OWNERS.get(tool, ())


def may_use_tools(assistant_id: str | None) -> bool:




    if not assistant_id:
        return False
    return any(assistant_id in owners for owners in TOOL_OWNERS.values())


def forbidden_tool_names(assistant_id: str | None) -> frozenset[str]:





    return frozenset(
        name for name in XJX_TOOL_NAMES if not may_use_tool(assistant_id, name)
    )





@lru_cache(maxsize=16)
def instructions(name: str) -> str:

    skill = _BY_NAME.get(name)
    if skill is None:
        raise KeyError(f"不是心鉴学内置技能：{name}")
    return read_text("xjx", skill.resource)


def skill_document(name: str) -> str:

    return instructions(name)


def describe(skill: XjxSkill) -> dict[str, Any]:






    from .. import groups  

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
        
        "bucket": groups.BUCKET_EXCLUSIVE,
        "locked": True,
        
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













    bad = sorted({item for item in names if is_reserved(item)})
    if not bad:
        return
    raise ValueError(
        f"「{'、'.join(bad)}」是内置专属技能：按当前线路自动启用、只属于对应的搭子，"
        "**不能写进技能清单** —— 写进去不会生效，还会把这个搭子的其它技能挤掉。"
        "专属技能不需要（也不允许）手动添加。"
    )


def locked_message(name: str) -> str:

    skill = _BY_NAME.get(name)
    if skill is not None:
        return (
            f"「{skill.display_name}」是 {skill.owner_label} 的内置专属技能："
            "按当前线路自动启用，不提供开关，也不能修改或删除。"
        )
    
    tool = name if name in XJX_TOOL_NAMES else next(
        (key for key, label in TOOL_DISPLAY.items() if label == name), ""
    )
    if tool:
        label = TOOL_DISPLAY.get(tool, tool)
        return (
            f"「{label}」是心鉴学专属技能的配套工具："
            "默认开启、免批准，不提供开关。"
        )
    return f"「{name}」是心鉴学内置技能，不提供开关。"


__all__ = [
    "GROUP_ASTRO",
    "GROUP_BAZI",
    "GROUP_BUDDIES",
    "GROUP_MEIHUA",
    "GROUP_SOULMATE",
    "GROUP_TAROT",
    "LINE_CN",
    "LINE_SEOUL",
    "OWNER_LABELS",
    "REPORT_PATHS",
    "TOOL_DISPLAY",
    "TOOL_FETCH_ASTRO",
    "TOOL_FETCH_BAZI",
    "TOOL_FETCH_MEIHUA",
    "TOOL_FETCH_REPORT",
    "TOOL_FETCH_TAROT",
    "TOOL_OWNERS",
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
    "may_use_tool",
    "may_use_tools",
    "reject_reserved_skill_names",
    "skill_by_name",
    "skill_document",
    "skills_for_assistant",
    "tool_owners",
]
