

































from __future__ import annotations

from collections.abc import Iterable, Mapping




BUCKET_MINE = "mine"
BUCKET_COMMON = "common"
BUCKET_BUILTIN = "builtin"
BUCKET_EXCLUSIVE = "exclusive"


BUCKETS: tuple[str, ...] = (BUCKET_MINE, BUCKET_COMMON, BUCKET_BUILTIN, BUCKET_EXCLUSIVE)

BUCKET_LABELS: dict[str, str] = {
    BUCKET_MINE: "我的技能",
    BUCKET_COMMON: "通用技能",
    BUCKET_BUILTIN: "内置技能",
    BUCKET_EXCLUSIVE: "专属技能",
}


























COMMON_NAMES: frozenset[str] = frozenset(
    {
        
        "system_volume",
        "system_volume_get",
        "system_brightness_get",
        "system_brightness_set",
        "system_lock_screen",
        
        "doc_word_to_markdown",
        "doc_markdown_to_word",
        "doc_to_pdf",
        "doc_pdf_to_text",
        "doc_parse",
        
        "excel_read",
        "excel_write",
        "excel_analyze",
        
        "weather_query",
        "expense_record",
        "expense_analyze",
        
        
        
        "paper_deweight",
        "humanizer",
        "pro_legal_strategist",
        "nihaixia",
    }
)










LOCKED_BUILTIN_NAMES: frozenset[str] = frozenset(
    {
        
        
        "system_time",
        "calc",
        
        "file_read",
        "file_write",
        
        "http_request",
        "http_fetch",
        
        "read_tool_output",
        
        "history_search",
        "kb_add",
        "kb_search",
        "kb_stats",
        "kb_forget",
        
        "self_persona_read",
        "self_persona_update",
        "self_growth",
        
        "plan_update",
        
        "ai_thinking_mode",
        
        "anti_fraud",
        
        "archive_list",
        "archive_read",
        
        
        
        
        
        "browser_read",
        "browser_act",
        "browser_screenshot",
        "browser_snapshot",
        "browser_tabs",
        
        "scheduled_task_create",
        "scheduled_task_delete",
        "scheduled_task_list",
        "scheduled_task_run",
        "scheduled_task_update",
        
        "clipboard_read_text",
        "clipboard_read_image",
        "clipboard_write",
        
        "calendar_create",
        "calendar_update",
        "calendar_list",
        "calendar_delete",
        
        "reminder_create",
        "reminder_list",
        "reminder_cancel",
        
        "chart_generate",
        "report_generate",
        "svg_create",
        
        "system_screenshot",
        
        "excerpo",
        "grill_me",
        "skill_creator",
    }
)







EXCLUSIVE_PREFIXES: tuple[str, ...] = ("team_", "buddy_", "computer_")
EXCLUSIVE_EXACT: frozenset[str] = frozenset(
    {
        "custom_skill_install",
        "skill_package_install",
        "update_assistant_profile",
        
        
        "pmaster",
        "dbskill",
    }
)


EXCLUSIVE_OWNER = "BuddyManager"









_OWNER_LABEL_EXTRA: dict[str, str] = {"BuddyManager": "Buddy Manager"}



























INSTRUCTION_EXCLUSIVE_OWNERS: dict[str, tuple[str, ...]] = {
    "brand-strategy": (EXCLUSIVE_OWNER,),
    "event-planning": (EXCLUSIVE_OWNER,),
    "funnel-analysis": (EXCLUSIVE_OWNER,),
    "marketing-playbooks": (EXCLUSIVE_OWNER,),
    "ab-test-setup": (EXCLUSIVE_OWNER,),
    "marketing-ideas": (EXCLUSIVE_OWNER,),
    "pricing-strategy": (EXCLUSIVE_OWNER,),
    "referral-program": (EXCLUSIVE_OWNER,),
}












ALWAYS_ON_INSTRUCTION_NAMES: frozenset[str] = frozenset(
    {"sensitive-data-precheck", "copy-editing"}
)


def is_locked_instruction(name: str) -> bool:











    return name in INSTRUCTION_EXCLUSIVE_OWNERS or name in ALWAYS_ON_INSTRUCTION_NAMES











RETIRED_COMMON_NAMES: frozenset[str] = frozenset(
    {"pmaster", "dbskill"}
    | set(INSTRUCTION_EXCLUSIVE_OWNERS)
    | ALWAYS_ON_INSTRUCTION_NAMES
)

















DOMAIN_ORDER: tuple[str, ...] = (
    "系统",
    "办公",
    "生活",
    "学术",
    "媒体",
    "法律",
    "医疗",
    "电商",
    "金融",
    "营销",
    "教育",
    "科技",
    "设计",
    "人力",
)




BUILTIN_DOMAINS: dict[str, str] = {
    
    "system_volume": "系统",
    "system_volume_get": "系统",
    "system_brightness_get": "系统",
    "system_brightness_set": "系统",
    "system_lock_screen": "系统",
    
    "doc_word_to_markdown": "办公",
    "doc_markdown_to_word": "办公",
    "doc_to_pdf": "办公",
    "doc_pdf_to_text": "办公",
    "doc_parse": "办公",
    
    "excel_read": "办公",
    "excel_write": "办公",
    "excel_analyze": "办公",
    
    "weather_query": "生活",
    "expense_record": "生活",
    "expense_analyze": "生活",
    
    "paper_deweight": "学术",
    "humanizer": "媒体",
    "pro_legal_strategist": "法律",
    "nihaixia": "医疗",
}


def domain_of(name: str, explicit: str = "") -> str:





    return explicit or BUILTIN_DOMAINS.get(name, "")


def owner_label(owners: Iterable[str]) -> str:

    from .builtin import xjx  

    labels = {**xjx.OWNER_LABELS, **_OWNER_LABEL_EXTRA}
    return "、".join(labels.get(item, item) for item in owners)





def is_exclusive(name: str) -> bool:

    if name in EXCLUSIVE_EXACT or name.startswith(EXCLUSIVE_PREFIXES):
        return True
    
    
    
    
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return True
    from .builtin import xjx

    
    
    
    return xjx.is_xjx_skill(name) or xjx.is_xjx_tool(name)


def without_exclusive(names: Iterable[str]) -> list[str]:











    return [name for name in names if not is_exclusive(name)]


def bucket_of(name: str, source: str, domain: str = "") -> str:










    
    
    
    
    
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return BUCKET_EXCLUSIVE
    if name in ALWAYS_ON_INSTRUCTION_NAMES:
        return BUCKET_BUILTIN
    if source == "custom":
        
        
        
        
        return BUCKET_COMMON if domain else BUCKET_MINE
    if source == "mcp":
        
        return BUCKET_COMMON
    if is_exclusive(name):
        return BUCKET_EXCLUSIVE
    if name in COMMON_NAMES:
        return BUCKET_COMMON
    
    return BUCKET_BUILTIN


def owners_of(name: str) -> tuple[str, ...]:

    from .builtin import xjx

    if xjx.is_xjx_skill(name):
        skill = xjx.skill_by_name(name)
        return skill.owners if skill is not None else ()
    if xjx.is_xjx_tool(name):
        
        
        
        
        return xjx.tool_owners(name)
    
    
    
    if name in INSTRUCTION_EXCLUSIVE_OWNERS:
        return INSTRUCTION_EXCLUSIVE_OWNERS[name]
    if name in EXCLUSIVE_EXACT or name.startswith(EXCLUSIVE_PREFIXES):
        return (EXCLUSIVE_OWNER,)
    return ()


def may_use_exclusive(name: str, assistant_id: str | None) -> bool:

    owners = owners_of(name)
    if not owners:
        return True
    return bool(assistant_id) and assistant_id in owners


def is_locked(name: str, source: str) -> bool:










    if source != "builtin":
        return False
    from .locked import ALWAYS_ON_SKILLS

    if name in ALWAYS_ON_SKILLS:
        return True
    if is_exclusive(name):
        return True
    
    return name in LOCKED_BUILTIN_NAMES





def forbidden_names(registered: Iterable[str], for_assistant: str | None) -> frozenset[str]:








    from .builtin import xjx

    blocked = set(xjx.forbidden_tool_names(for_assistant))
    
    
    
    for name in EXCLUSIVE_EXACT:
        if not may_use_exclusive(name, for_assistant):
            blocked.add(name)
    for name in registered:
        if is_exclusive(name) and not may_use_exclusive(name, for_assistant):
            blocked.add(name)
    return frozenset(blocked)


def allowed_skill_names(
    sources: Mapping[str, str],
    *,
    assistant_id: str | None,
    enabled_skills: Iterable[str] | None,
    builtin_assistant: bool,
) -> set[str]:








    allowed = {
        name
        for name, source in sources.items()
        if bucket_of(name, source) == BUCKET_BUILTIN
    }

    
    
    
    
    
    
    
    
    allowed |= ALWAYS_ON_INSTRUCTION_NAMES

    
    
    
    
    allowed |= {
        name
        for name in INSTRUCTION_EXCLUSIVE_OWNERS
        if may_use_exclusive(name, assistant_id)
    }

    if builtin_assistant:
        
        
        
        
        
        
        allowed |= {
            name
            for name, source in sources.items()
            if bucket_of(name, source) == BUCKET_EXCLUSIVE
            and may_use_exclusive(name, assistant_id)
        }

    
    
    
    for name in set(enabled_skills or ()):
        source = sources.get(name)
        if source is None:
            
            
            
            
            
            
            
            
            
            
            
            if name in INSTRUCTION_EXCLUSIVE_OWNERS:
                continue
            allowed.add(name)
            continue
        if bucket_of(name, source) in (BUCKET_COMMON, BUCKET_MINE):
            allowed.add(name)
    return allowed





def validate_registry(registered: Iterable[str]) -> list[str]:










    known = set(registered)
    missing = [name for name in sorted(COMMON_NAMES) if name not in known]
    missing += [name for name in sorted(EXCLUSIVE_EXACT) if name not in known]
    return missing






