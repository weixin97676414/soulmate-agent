"""Skill 系统：核心抽象层。"""

from .base import BaseSkill, ConfirmRequest, SkillContext, SkillMeta
from .decorator import skill
from .manager import SkillManager, stringify_result

__all__ = [
    "BaseSkill",
    "ConfirmRequest",
    "SkillContext",
    "SkillManager",
    "SkillMeta",
    "skill",
    "stringify_result",
]
