





from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any






class McpServerState(str, Enum):  


    DISABLED = "disabled"  
    STOPPED = "stopped"  
    STARTING = "starting"  
    READY = "ready"  
    RESTARTING = "restarting"  
    ERROR = "error"  



ACTIVE_STATES = frozenset({McpServerState.READY})


@dataclass
class McpToolInfo:


    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    
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








    name: str
    state: McpServerState = McpServerState.STOPPED
    message: str = ""
    tools: list[McpToolInfo] = field(default_factory=list)
    
    
    
    
    
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
    
    sdk_missing: bool = False

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @classmethod
    def from_config(cls, config: Any, **overrides: Any) -> McpServerStatus:

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
