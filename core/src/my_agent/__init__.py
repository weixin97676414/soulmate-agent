"""自研智能体框架核心（Agent Core）。

面向办公职场与日常生活场景，轻量、可控、可扩展。
对应《智能体框架开发文档》第 13.1 节的公共 API 出口。
"""

from .agent.engine import Agent, AgentConfig, AgentEvent
from .agent.session import Session, SessionManager
from .config.loader import ConfigStore
from .config.paths import AppPaths
from .config.schemas import AppConfig, AppSettings, ModelsConfig, ModelSpec
from .errors import AgentError
from .llm import BaseLLM, LlmRegistry, Message, ToolCall, ToolSpec
from .memory.short_term import MemoryManager
from .observability.tracer import Tracer
from .security.permission import PermissionGuard
from .skill import BaseSkill, SkillContext, SkillManager, SkillMeta, skill
from .storage import AuditRepository, Database, SessionRepository, WorkspaceStore

# 版本号的唯一来源在 version.py（见那里的说明），这里只是重新导出，
# 保持 `my_agent.__version__` 这个既有写法继续可用
from .version import __version__  # noqa: E402  (排在公共 API 导入之后，便于阅读)

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentError",
    "AgentEvent",
    "AppConfig",
    "AppPaths",
    "AppSettings",
    "AuditRepository",
    "BaseLLM",
    "BaseSkill",
    "ConfigStore",
    "Database",
    "LlmRegistry",
    "MemoryManager",
    "Message",
    "ModelSpec",
    "ModelsConfig",
    "PermissionGuard",
    "Session",
    "SessionManager",
    "SessionRepository",
    "SkillContext",
    "SkillManager",
    "SkillMeta",
    "ToolCall",
    "ToolSpec",
    "Tracer",
    "WorkspaceStore",
    "skill",
    "__version__",
]
