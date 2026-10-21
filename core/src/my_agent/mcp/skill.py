







from __future__ import annotations

import asyncio
import hashlib
import re
from typing import TYPE_CHECKING, Any

from ..skill.base import BaseSkill, SkillContext, SkillMeta
from .types import McpToolInfo

if TYPE_CHECKING:
    from .client import McpClient



_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_NAME_MAX = 64


READ_TOKENS = frozenset(
    {
        "read", "list", "get", "query", "search", "find", "stat", "describe",
        "head", "info", "show", "view", "fetch", "lookup", "count", "exists",
        "check", "peek", "inspect", "export", "download", "resolve", "match",
        "grep", "scan", "diff", "compare", "history", "status", "preview",
    }
)







WRITE_TOKENS = frozenset(
    {
        "write", "create", "add", "insert", "update", "edit", "modify", "set",
        "delete", "remove", "drop", "clear", "reset", "truncate", "unlink",
        "move", "rename", "copy", "mkdir", "touch", "chmod", "chown",
        "execute", "run", "exec", "spawn", "kill", "install", "uninstall",
        "start", "stop", "restart", "send", "post", "put", "patch", "upload",
        "push", "publish", "submit", "apply", "commit", "merge", "format",
        
        "replace", "transform", "convert", "save", "store", "append",
        "purge", "wipe", "sync", "revoke", "grant", "assign", "rotate",
        "register", "deregister", "enable", "disable", "lock", "unlock",
        "increment", "decrement", "import", "restore", "revert", "rollback",
        "schedule", "cancel", "retry", "invoke", "trigger", "notify",
        "rename_move", "link", "symlink", "extract", "deploy", "release",
    }
)


_WORD_SPLIT = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z0-9]+")


def _tokens(name: str) -> set[str]:





    tokens: set[str] = set()
    for chunk in re.split(r"[^A-Za-z0-9]+", name or ""):
        if not chunk:
            continue
        tokens.add(chunk.lower())
        for word in _WORD_SPLIT.findall(chunk):
            tokens.add(word.lower())
    return tokens


def _hit(tokens: set[str], vocabulary: frozenset[str]) -> bool:
    for token in tokens:
        if token in vocabulary:
            return True
        
        if token.endswith("s") and token[:-1] in vocabulary:
            return True
    return False


def infer_permission_level(tool: McpToolInfo) -> str:












    if tool.destructive is True:
        return "confirm"
    if tool.read_only is True:
        return "safe"

    tokens = _tokens(tool.name)
    if _hit(tokens, WRITE_TOKENS):
        return "confirm"
    if _hit(tokens, READ_TOKENS):
        return "safe"
    return "confirm"


def namespaced_name(server: str, tool: str) -> str:









    raw = f"{server}__{tool}"
    cleaned = _NAME_SAFE.sub("_", raw)

    
    
    
    
    if "__" in server or "__" in tool:
        digest = hashlib.sha1(f"{server}\x00{tool}".encode()).hexdigest()[:6]
        cleaned = f"{cleaned[: _NAME_MAX - 7]}_{digest}"

    if len(cleaned) <= _NAME_MAX:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[: _NAME_MAX - 9]}_{digest}"


def build_mcp_skill(
    client: McpClient,
    tool: McpToolInfo,
    *,
    permission_level: str,
) -> BaseSkill:






    server = client.server_name
    tool_name = namespaced_name(server, tool.name)
    description = tool.description.strip() or f"{server} 提供的工具 {tool.name}"

    meta = SkillMeta(
        name=tool_name,
        display_name=f"{tool.title or tool.name}",
        
        description=f"[{server}] {description}",
        parameters=tool.input_schema or {"type": "object", "properties": {}},
        category="mcp",
        permission_level=permission_level,
        timeout=client.config.timeout,
        source="mcp",
        tags=[server, tool.name],
    )

    class _McpToolSkill(BaseSkill):












        async def run(self, ctx: SkillContext, **params: Any) -> Any:
            from ..errors import McpServerError, SkillExecutionError

            if not client.is_ready:
                raise SkillExecutionError(
                    f"MCP Server「{server}」当前不可用，工具 {tool.name} 无法执行。"
                    f"请在「设置 → MCP 服务」中检查连接状态。"
                )
            try:
                return await client.call_tool(tool.name, params)
            except McpServerError as exc:
                raise SkillExecutionError(exc.message) from exc
            except asyncio.CancelledError:
                raise
            except Exception as exc:  
                
                
                
                
                raise SkillExecutionError(
                    f"MCP Server「{server}」的工具 {tool.name} 执行失败：{exc}"
                ) from exc

    _McpToolSkill.meta = meta
    _McpToolSkill.__name__ = f"McpToolSkill_{tool_name}"
    _McpToolSkill.__qualname__ = _McpToolSkill.__name__
    instance = _McpToolSkill()
    
    instance.mcp_server = server  
    instance.mcp_tool = tool.name  
    instance.mcp_client = client  
    return instance


__all__ = [
    "READ_TOKENS",
    "WRITE_TOKENS",
    "build_mcp_skill",
    "infer_permission_level",
    "namespaced_name",
]
