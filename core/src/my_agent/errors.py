





from __future__ import annotations


class AgentError(Exception):


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





class ConfigError(AgentError):
    code = "config_error"
    http_status = 500





class LLMError(AgentError):
    code = "llm_error"
    http_status = 502


class LLMAuthError(LLMError):


    code = "llm_auth_error"
    http_status = 401


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    http_status = 504


class ContextOverflowError(LLMError):


    code = "context_overflow"
    http_status = 413





class SkillError(AgentError):
    code = "skill_error"


class SkillNotFoundError(SkillError):
    code = "skill_not_found"
    http_status = 404


class SkillPermissionError(SkillError):


    code = "skill_permission_denied"
    http_status = 403


class SkillTimeoutError(SkillError):
    code = "skill_timeout"
    http_status = 504


class SkillExecutionError(SkillError):
    code = "skill_execution_error"


class SkillValidationError(SkillError):


    code = "skill_validation_error"
    http_status = 422





class McpServerError(AgentError):






    code = "mcp_error"
    http_status = 502


class McpSdkMissingError(McpServerError):


    code = "mcp_sdk_missing"
    http_status = 501

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "未安装 MCP 依赖，无法连接 MCP Server。"
            "请执行：pip install \"my-agent-core[mcp]\""
        )


class McpUnavailableError(McpServerError):


    code = "mcp_unavailable"


class McpToolCallError(McpServerError):


    code = "mcp_tool_error"





class PathNotAllowedError(SkillError):


    code = "path_not_allowed"
    http_status = 403





class SessionNotFoundError(AgentError):
    code = "session_not_found"
    http_status = 404


class ScheduledTaskNotFoundError(AgentError):







    code = "scheduled_task_not_found"
    http_status = 404


class AgentMaxIterationsError(AgentError):


    code = "agent_max_iterations"
    http_status = 409


class AgentCancelledError(AgentError):
    code = "agent_cancelled"
    http_status = 409
