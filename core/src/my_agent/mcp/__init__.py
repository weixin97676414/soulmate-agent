"""MCP（Model Context Protocol）集成。

把第三方 MCP Server 的工具自动包装成 Skill，纳入统一的工具列表交给模型
（开发文档第 6 章）。官方 ``mcp`` SDK 是**可选依赖**，未安装时本模块
依然可以导入，只是所有 Server 会被标记为「依赖缺失」。
"""

from .client import McpClient, sdk_available
from .manager import MAX_AUTO_RESTARTS, McpManager
from .presets import build_sample_server, presets, sample_server_args
from .skill import build_mcp_skill, infer_permission_level, namespaced_name
from .types import McpServerState, McpServerStatus, McpToolInfo

__all__ = [
    "MAX_AUTO_RESTARTS",
    "McpClient",
    "McpManager",
    "McpServerState",
    "McpServerStatus",
    "McpToolInfo",
    "build_mcp_skill",
    "build_sample_server",
    "infer_permission_level",
    "namespaced_name",
    "presets",
    "sample_server_args",
    "sdk_available",
]
