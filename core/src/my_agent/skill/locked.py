












































from __future__ import annotations





ALWAYS_ON_SKILLS: frozenset[str] = frozenset(
    {
        "ai_thinking_mode",
        "system_time",
        "self_growth",
        "history_search",
        "kb_add",
        "kb_search",
        "kb_stats",
        "anti_fraud",
        "http_request",
        
        
        "xjx_place_lookup",
        "xjx_fetch_report",
        
        "xjx_fetch_astro",
        "xjx_fetch_bazi",
        "xjx_fetch_meihua",
        "xjx_fetch_tarot",
        
        
        
        
        
        
        
        
        "ask_choice",
        "request_secret",
    }
)



RESERVED_SKILL_NAMES: frozenset[str] = frozenset(
    {"Soulmate专用", "人际关系运营", "地点核对", "报告代取"}
) | ALWAYS_ON_SKILLS


def is_always_on(name: str) -> bool:

    return name in ALWAYS_ON_SKILLS


def is_reserved(name: str) -> bool:






    if name in RESERVED_SKILL_NAMES:
        return True
    from .builtin import xjx

    return xjx.is_reserved(name)


def locked_message(display_name: str) -> str:






    from .builtin import xjx

    if xjx.is_reserved(display_name):
        return xjx.locked_message(display_name)
    
    
    
    
    if display_name in {"ask_choice", "request_secret", "请你确认一下", "请你提供密钥"}:
        return (
            f"「{display_name}」是默认永久开启的技能：搭子拿不准你的意思、"
            "或需要你提供密钥时，靠它停下来问你，而不是自己猜。"
            "不提供开关，也不能修改权限。"
        )
    return (
        f"「{display_name}」是默认永久开启的技能：它承载搭子的长期记忆与基础能力，"
        "不提供开关，也不能修改权限。"
    )
