"""MCP 领域的数据结构与状态枚举。

这些类型**不依赖官方 SDK**，因此界面层与状态展示可以在没装 `mcp` 依赖时
照常工作（只把服务标成「依赖缺失」即可）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# 刻意**不**改成 StrEnum：两者的 ``str()`` 行为不同 —— ``(str, Enum)`` 给出
# ``"McpServerState.READY"``，而 ``StrEnum`` 给出 ``"ready"``。这个值会进指标标签
# （见 McpManager 的 ``METRICS.inc(..., state=status.state)``）与 JSON 输出，
# 改过去等于悄悄换了对外契约 —— 为一条纯风格规则冒这个险不值得。
class McpServerState(str, Enum):  # noqa: UP042
    """一个 MCP Server 的连接状态。"""

    DISABLED = "disabled"  # 用户在界面上关掉了
    STOPPED = "stopped"  # 已配置但未连接
    STARTING = "starting"  # 正在启动子进程 / 握手
    READY = "ready"  # 已连接，工具可用
    RESTARTING = "restarting"  # 崩溃后自动重连中
    ERROR = "error"  # 连接失败或已断开


# 状态对应的「工具是否可用」：只有 READY 才把工具交给模型
ACTIVE_STATES = frozenset({McpServerState.READY})


@dataclass
class McpToolInfo:
    """一个 MCP 工具的元信息（已从 SDK 类型归一化）。"""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    # 来自 MCP 的 ToolAnnotations，是权限推断最可靠的依据
    read_only: bool | None = None
    destructive: bool | None = None
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "input_schema": self.input_schema,
            "read_only": self.read_only,
            "destructive": self.destructive,
        }


@dataclass
class McpServerStatus:
    """对外（接口层 / 界面）暴露的服务状态快照。

    **完整带上启动配置（含 env）**，而不是只给一部分：设置界面是「读取 → 编辑 →
    整体保存」的交互，如果这里不返回 env，用户随便点一下开关就会把自己填过的
    环境变量清空。这些值本来就是用户自己在本机配置文件里写的，回传给自己的
    界面不构成额外的信息暴露。
    """

    name: str
    state: McpServerState = McpServerState.STOPPED
    message: str = ""
    tools: list[McpToolInfo] = field(default_factory=list)
    # 传输方式与远程端点。**必须回传**，否则界面「读取 → 编辑 → 整体保存」
    # 会把它们一并丢掉：``transport`` 退回默认的 ``stdio``，而远程传输又必填
    # ``command``，结果是用户点一下开关就收到 422"stdio 传输必须填写启动命令"；
    # 若 ``command`` 恰好非空，则更糟 —— 服务被**静默**从远程降级成 stdio，
    # 而界面上看不出任何变化。
    transport: str = "stdio"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    enabled: bool = True
    auto_start: bool = True
    description: str = ""
    timeout: float = 60.0
    permission_overrides: dict[str, str] = field(default_factory=dict)
    restarts: int = 0
    last_error: str | None = None
    # 官方 SDK 未安装时为 True，界面据此给出安装指引
    sdk_missing: bool = False

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @classmethod
    def from_config(cls, config: Any, **overrides: Any) -> McpServerStatus:
        """按配置初始化一份状态快照。"""
        return cls(
            name=config.name,
            transport=config.transport,
            url=config.url,
            headers=dict(config.headers),
            command=config.command,
            args=list(config.args),
            env=dict(config.env),
            cwd=config.cwd,
            enabled=config.enabled,
            auto_start=config.auto_start,
            description=config.description,
            timeout=config.timeout,
            permission_overrides=dict(config.permission_overrides),
            **overrides,
        )

    def sync_from_config(self, config: Any) -> None:
        """把配置里的可编辑字段同步到状态上（配置变更后调用）。"""
        self.transport = config.transport
        self.url = config.url
        self.headers = dict(config.headers)
        self.command = config.command
        self.args = list(config.args)
        self.env = dict(config.env)
        self.cwd = config.cwd
        self.enabled = config.enabled
        self.auto_start = config.auto_start
        self.description = config.description
        self.timeout = config.timeout
        self.permission_overrides = dict(config.permission_overrides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "message": self.message,
            "tools": [tool.to_dict() for tool in self.tools],
            "tool_count": self.tool_count,
            "transport": self.transport,
            "url": self.url,
            "headers": dict(self.headers),
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "cwd": self.cwd,
            "enabled": self.enabled,
            "auto_start": self.auto_start,
            "description": self.description,
            "timeout": self.timeout,
            "permission_overrides": dict(self.permission_overrides),
            "restarts": self.restarts,
            "last_error": self.last_error,
            "sdk_missing": self.sdk_missing,
        }
