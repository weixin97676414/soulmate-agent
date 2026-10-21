




















from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from ..config.schemas import McpServerConfig
from ..errors import McpSdkMissingError, PathNotAllowedError
from ..security.paths import PathPolicy

logger = logging.getLogger(__name__)


def validate_cwd(config: McpServerConfig, policy: PathPolicy | None = None) -> str | None:





















    raw = (config.cwd or "").strip()
    if not raw:
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        
        
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 必须是绝对路径：{raw}")
    if not path.exists():
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 不存在：{path}")
    if not path.is_dir():
        raise ValueError(f"MCP 服务「{config.name}」的 cwd 不是目录：{path}")

    if policy is not None and policy.is_restricted:
        try:
            policy.check(str(path), mode="read")
        except PathNotAllowedError as exc:
            raise ValueError(
                f"MCP 服务「{config.name}」的 cwd（{path}）不在允许的目录白名单内。"
                f"当前白名单：{policy.describe()}。"
                "如果这个服务确实需要在该目录运行，请先把它加进"
                "「设置 → 工作区 → 允许目录」。"
            ) from exc

    return str(path)


def _remote_headers(config: McpServerConfig) -> dict[str, str] | None:
    return dict(config.headers) or None


async def open_transport(
    config: McpServerConfig, stack: AsyncExitStack, policy: PathPolicy | None = None
) -> tuple[Any, Any]:









    if config.transport == "stdio":
        return await _open_stdio(config, stack, policy)
    if config.transport == "sse":
        return await _open_sse(config, stack)
    if config.transport == "streamable_http":
        return await _open_streamable_http(config, stack)
    raise ValueError(f"不支持的 MCP 传输方式：{config.transport}")


async def _open_stdio(
    config: McpServerConfig, stack: AsyncExitStack, policy: PathPolicy | None = None
) -> tuple[Any, Any]:
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    from .client import build_subprocess_env

    cwd = validate_cwd(config, policy)
    params = StdioServerParameters(
        command=config.command,
        args=list(config.args),
        
        env=build_subprocess_env(config.env),
        cwd=cwd,
    )
    return await stack.enter_async_context(stdio_client(params))


async def _open_sse(config: McpServerConfig, stack: AsyncExitStack) -> tuple[Any, Any]:
    try:
        from mcp.client.sse import sse_client
    except ImportError as exc:  
        raise McpSdkMissingError(
            "当前安装的 mcp 版本不支持 SSE 传输，请升级：pip install -U \"my-agent-core[mcp]\""
        ) from exc

    logger.info("MCP 服务 %s 使用 SSE 传输连接 %s", config.name, config.url)
    streams = await stack.enter_async_context(
        sse_client(config.url, headers=_remote_headers(config))
    )
    
    read, write = streams[0], streams[1]
    return read, write


async def _open_streamable_http(
    config: McpServerConfig, stack: AsyncExitStack
) -> tuple[Any, Any]:
    try:
        
        
        
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  
        raise McpSdkMissingError(
            "当前安装的 mcp 版本不支持 Streamable HTTP 传输，"
            "请升级：pip install -U \"my-agent-core[mcp]\""
        ) from exc

    
    
    
    
    http_client = None
    headers = _remote_headers(config)
    if headers:
        try:
            from mcp.shared._httpx_utils import create_mcp_http_client

            http_client = create_mcp_http_client(headers=headers)
        except ImportError:  
            logger.warning(
                "MCP 服务 %s 需要自定义请求头，但当前 mcp 版本没有可用的 http 客户端工厂；"
                "本次连接将不带这些头。",
                config.name,
            )

    logger.info("MCP 服务 %s 使用 Streamable HTTP 连接 %s", config.name, config.url)
    
    
    if http_client is not None:
        stack.push_async_callback(http_client.aclose)
    streams = await stack.enter_async_context(
        streamable_http_client(config.url, http_client=http_client)
    )
    
    
    return streams[0], streams[1]


def transport_summary(config: McpServerConfig) -> str:

    if config.transport == "stdio":
        return f"{config.command} {' '.join(config.args)}".strip()
    return config.url
