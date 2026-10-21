






from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)




_MODULES: list[str] = [
    
    "my_agent.skill.builtin.system",
    
    
    
    "my_agent.skill.builtin.http_tools",
    "my_agent.skill.builtin.file_tools",
    
    
    "my_agent.skill.builtin.output_read",
    
    "my_agent.skill.builtin.browser",
    
    
    "my_agent.skill.builtin.task_tools",
    
    
    
    "my_agent.skill.builtin.clipboard",
    "my_agent.skill.builtin.system_control",
    
    "my_agent.skill.builtin.doc_convert",
    
    "my_agent.skill.builtin.office.excel",
    "my_agent.skill.builtin.office.document",
    "my_agent.skill.builtin.office.report",
    "my_agent.skill.builtin.office.chart",
    
    
    "my_agent.skill.builtin.svg_tools",
    
    "my_agent.skill.builtin.life.weather",
    "my_agent.skill.builtin.life.expense",
    "my_agent.skill.builtin.life.reminder",
    
    "my_agent.skill.builtin.calendar",
    
    "my_agent.skill.builtin.knowledge",
    
    "my_agent.skill.builtin.self_persona",
    
    
    "my_agent.skill.builtin.profile_tools",
    
    
    "my_agent.skill.builtin.buddy_tools",
    
    
    
    "my_agent.skill.builtin.orchestrate",
    
    "my_agent.skill.builtin.history_search",
    
    
    "my_agent.skill.builtin.plan_tools",
    
    "my_agent.skill.builtin.archive",
    
    "my_agent.skill.builtin.ai_thinking_mode",
    
    "my_agent.skill.builtin.self_growth",
    
    "my_agent.skill.builtin.content_skills",
    
    "my_agent.skill.builtin.domain_skills",
    
    
    
    
    "my_agent.skill.builtin.geo_lookup",
    "my_agent.skill.builtin.xjx_report",
    
    
    
    "my_agent.skill.builtin.xjx_charts",
    
    
    
    
    "my_agent.skill.builtin.computer",
    
    
    
    
    
    "my_agent.skill.builtin.ask_choice",
    "my_agent.skill.builtin.request_secret",
]


def discover_builtin_skills() -> list[type]:

    from ..base import BaseSkill

    found: list[type] = []
    for module_path in _MODULES:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            logger.error("内置 Skill 模块导入失败 %s: %s", module_path, exc)
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
                and getattr(attr, "meta", None) is not None
            ):
                found.append(attr)
                logger.debug("发现内置 Skill: %s", attr.meta.name)
    return found
