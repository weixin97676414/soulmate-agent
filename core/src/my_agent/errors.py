"""统一异常体系。

所有业务异常继承 ``AgentError``，携带可读 message 与错误码，
便于服务层统一转换为 HTTP 响应（见 ``server.error_handlers``）。
"""

from __future__ import annotations


class AgentError(Exception):
    """框架所有业务异常的基类。"""

    code: str = "agent_error"
    http_status: int = 400

    def __init__(self, message: str, *, code: str | None = None, detail: object = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.detail = detail

    def to_dict(self) -> dict:
        data = {"code": self.code, "message": self.message}
        if self.detail is not None:
            data["detail"] = self.detail
        return data


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
class ConfigError(AgentError):
    code = "config_error"
    http_status = 500


# --------------------------------------------------------------------------- #
# LLM 接入层
# --------------------------------------------------------------------------- #
class LLMError(AgentError):
    code = "llm_error"
    http_status = 502


class LLMAuthError(LLMError):
    """API Key 无效或缺失。"""

    code = "llm_auth_error"
    http_status = 401


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    http_status = 504


class ContextOverflowError(LLMError):
    """上下文超限，应由 MemoryManager 截断后重试。"""

    code = "context_overflow"
    http_status = 413


# --------------------------------------------------------------------------- #
# Skill 系统
# --------------------------------------------------------------------------- #
class SkillError(AgentError):
    code = "skill_error"


class SkillNotFoundError(SkillError):
    code = "skill_not_found"
    http_status = 404


class SkillPermissionError(SkillError):
    """权限校验未通过，或用户拒绝执行。"""

    code = "skill_permission_denied"
    http_status = 403


class SkillTimeoutError(SkillError):
    code = "skill_timeout"
    http_status = 504


class SkillExecutionError(SkillError):
    code = "skill_execution_error"


class SkillValidationError(SkillError):
    """参数不符合 Schema。"""

    code = "skill_validation_error"
    http_status = 422


# --------------------------------------------------------------------------- #
# MCP
# --------------------------------------------------------------------------- #
class McpServerError(AgentError):
    """MCP 相关的通用错误。

    命名上刻意避开 ``McpError``：官方 SDK 里已有同名异常，
    两者混在一起会让排查问题的人非常困惑。
    """

    code = "mcp_error"
    http_status = 502


class McpSdkMissingError(McpServerError):
    """未安装可选的 mcp 依赖。"""

    code = "mcp_sdk_missing"
    http_status = 501

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "未安装 MCP 依赖，无法连接 MCP Server。"
            "请执行：pip install \"my-agent-core[mcp]\""
        )


class McpUnavailableError(McpServerError):
    """目标 Server 当前不可用（未连接 / 正在重启 / 已崩溃）。"""

    code = "mcp_unavailable"


class McpToolCallError(McpServerError):
    """MCP 工具执行返回了错误结果。"""

    code = "mcp_tool_error"


# --------------------------------------------------------------------------- #
# 文件访问
# --------------------------------------------------------------------------- #
class PathNotAllowedError(SkillError):
    """路径不在白名单内。"""

    code = "path_not_allowed"
    http_status = 403


# --------------------------------------------------------------------------- #
# 会话与任务
# --------------------------------------------------------------------------- #
class SessionNotFoundError(AgentError):
    code = "session_not_found"
    http_status = 404


class ScheduledTaskNotFoundError(AgentError):
    """定时任务不存在。

    单独一个类型（而不是复用 ConfigError）是为了让 HTTP 层能给出 404：
    用户点了"删除"但任务已经不在（另一个窗口删过、或配置文件被手改过）时，
    返回 500 会让人以为"应用坏了"，而它其实只是"你要找的东西不在了"。
    """

    code = "scheduled_task_not_found"
    http_status = 404


class AgentMaxIterationsError(AgentError):
    """达到最大循环轮数仍未收敛。"""

    code = "agent_max_iterations"
    http_status = 409


class AgentCancelledError(AgentError):
    code = "agent_cancelled"
    http_status = 409
